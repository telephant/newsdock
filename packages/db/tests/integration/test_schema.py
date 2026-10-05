"""TC-34 + TC-14: migrations match the ORM metadata; cascade works (needs Docker).

Runs in its own compose project (`newsdock-db-test`) against `.env.example`
values, so a real dev stack and the owner's `.env` are untouched. Needs port
5433 free.
"""

import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from newsdock_db.engine import make_engine
from newsdock_db.metadata import metadata
from newsdock_db.models import Analysis, Article, IngestSlot
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-db-test"


def _env_example() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    env = _env_example()
    up = _compose("up", "-d", "--wait", "postgres")
    assert up.returncode == 0, up.stderr
    port = env.get("POSTGRES_PORT", "5433")
    yield (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{port}/{env['POSTGRES_DB']}"
    )
    _compose("down", "-v", "--remove-orphans")


@pytest.fixture()
def migrated_url(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = Config(str(ROOT / "infra" / "migrations" / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield database_url
    engine = make_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM analyses"))
        conn.execute(text("DELETE FROM articles"))
    engine.dispose()


def test_upgrade_head_is_idempotent(migrated_url: str) -> None:
    cfg = Config(str(ROOT / "infra" / "migrations" / "alembic.ini"))
    command.upgrade(cfg, "head")  # second run must be a no-op, not an error


# TC-34: hand-written migrations and ORM metadata do not drift
def test_autogenerate_is_a_noop(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    engine.dispose()
    assert diff == [], f"schema drift between models and migrations: {diff}"


def _article(key: str) -> Article:
    now = datetime.now(UTC)
    return Article(
        url_hash=key, gkg_record_id="20261004081500-1", slot="20261004081500",
        url=f"https://example.com/{key}", title="t", domain="example.com",
        published_at=now, themes=["ECON_TEST"], persons=[], orgs=[],
        tone=1.0, tone_pos=1.0, tone_neg=0.0, tone_polarity=1.0, word_count=10,
    )  # fmt: skip


# TC-14: deleting an article cascades to its analyses
def test_delete_cascades_to_analyses(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        session.add(_article("h1"))
        session.commit()  # articles first: no relationship() orders the inserts
        session.add(
            Analysis(article_id="h1", agent_name="demo", payload={"score": 0.9})
        )
        session.commit()
        session.delete(session.get(Article, "h1"))
        session.commit()
        assert session.execute(select(Analysis)).all() == []
    engine.dispose()


def test_ingest_slot_roundtrip_and_roles(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        session.add(IngestSlot(slot="20261004081500", status="pending"))
        session.commit()
        stored = session.get(IngestSlot, "20261004081500")
        assert stored is not None and stored.attempts == 0
        roles = session.execute(
            text(
                "SELECT rolname FROM pg_roles WHERE rolname IN "
                "('ingester_rw','sink_rw','api_rw')"
            )
        ).scalars().all()  # fmt: skip
        assert sorted(roles) == ["api_rw", "ingester_rw", "sink_rw"]
    engine.dispose()
