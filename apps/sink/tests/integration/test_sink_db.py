"""TC-12, TC-13 against real Postgres (Docker): cross-slot dedup and retention."""

import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_core.contracts import CleanArticle
from newsdock_db.engine import make_engine
from newsdock_db.models import Article
from newsdock_sink.adapters.db import SqlArticleWriter
from newsdock_sink.domain.retention import cutoff
from newsdock_sink.domain.writer import SinkItem, process_batch
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
PROJECT = "newsdock-sink-test"
SLOT = "20261004081500"
BASE = "http://x"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def engine_url(request: pytest.FixtureRequest) -> Iterator[str]:
    assert _compose("up", "-d", "--wait", "postgres").returncode == 0
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in (ROOT / ".env.example").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{env.get('POSTGRES_PORT', '5433')}/{env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    mp.undo()
    yield url
    _compose("down", "-v", "--remove-orphans")


@pytest.fixture()
def clean_db(engine_url: str) -> Iterator[str]:
    engine = make_engine(engine_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE ingest_slot"))
    engine.dispose()
    yield engine_url


class NullDlq:
    def send(self, key: str, message: object) -> None:
        raise AssertionError(f"unexpected dlq message for {key}")


def _count(url: str) -> int:
    engine = make_engine(url)
    with Session(engine) as session:
        n = session.scalar(select(func.count()).select_from(Article))
    engine.dispose()
    return int(n or 0)


# TC-12: the same URL in two different slots stores one article
def test_cross_slot_dedup(clean_db: str) -> None:
    with (FIXTURES / "expected_articles.json").open() as f:
        article = CleanArticle.model_validate(json.load(f)[0])
    other_slot = article.model_copy(update={"slot": "20261004083000"})
    engine = make_engine(clean_db)
    writer = SqlArticleWriter(engine)
    result = process_batch(
        [
            SinkItem(key=a.url_hash, value=a.model_dump_json().encode())
            for a in (article, other_slot)
        ],
        writer,
        NullDlq(),
    )
    assert result.written == 1 and result.conflicts == 1
    assert _count(clean_db) == 1
    engine.dispose()


# TC-13: with an injected clock, the 8-day article is gone, the 6-day one kept
def test_retention_deletes_only_older_than_seven_days(clean_db: str) -> None:
    now = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
    engine = make_engine(clean_db)
    with Session(engine) as session:
        for age_days, key in ((8, "old"), (6, "fresh")):
            session.add(Article(
                url_hash=key, gkg_record_id="x", slot=SLOT,
                url=f"https://e.com/{key}", title=key, domain=None,
                published_at=now, ingested_at=now - timedelta(days=age_days),
                themes=[], persons=[], orgs=[],
            ))  # fmt: skip
        session.commit()
    deleted = SqlArticleWriter(engine).delete_ingested_before(cutoff(now))
    assert deleted == 1
    with Session(engine) as session:
        remaining = session.scalars(select(Article.url_hash)).all()
    assert remaining == ["fresh"]
    engine.dispose()
