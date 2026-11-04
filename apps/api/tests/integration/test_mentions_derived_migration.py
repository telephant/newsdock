"""TC-3 (AC-3): migration 0013 adds `mentions.derived` and backfills (Docker).

Rows are inserted with plain SQL at revision 0012, before the column exists.
Runs against a throwaway Postgres from `side_db`; the dev database is never touched.
"""

import importlib.util
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from newsdock_db.engine import make_engine
from newsdock_db.metadata import metadata
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
MIGRATION_FILE = ROOT / "infra/migrations/versions/0013_mentions_derived.py"
MENTION = (
    "INSERT INTO mentions (event_id, url_hash, url, mention_time, ingested_at) "
    "VALUES (:e, :h, :u, '2026-11-02 11:00+00', '2026-11-02 12:00+00')"
)


def _config() -> Config:
    return Config(str(ROOT / "infra" / "migrations" / "alembic.ini"))


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE mentions"))
        conn.execute(
            text(
                "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                "domain, published_at, themes, persons, orgs, story_key) VALUES "
                "('C', 'x', '20261102110000', 'https://c.com/C', 'T', 'c.com', "
                "now(), '{}', '{}', '{}', 's c')"
            )
        )
        for key in ("C", "X", "Y"):  # the canonical's own source and two copies
            conn.execute(
                text(
                    "INSERT INTO article_sources (url_hash, article_id, url, domain, "
                    "slot, gkg_record_id, published_at) VALUES "
                    "(:k, 'C', :u, 'd.com', '20261102110000', 'x', now())"
                ),
                {"k": key, "u": f"https://d.com/{key}"},
            )
        for event_id, key in ((7, "X"), (7, "Y"), (8, "C"), (9, "unknown")):
            conn.execute(text(MENTION), {"e": event_id, "h": key, "u": f"u/{key}"})


def _rows(engine: Engine) -> list[tuple[int, str, bool]]:
    with engine.connect() as conn:
        return [
            (int(e), str(h), bool(d))
            for e, h, d in conn.execute(
                text(
                    "SELECT event_id, url_hash, derived FROM mentions "
                    "ORDER BY event_id, url_hash"
                )
            )
        ]


def test_migration_0013_backfills_derived_rows_once_and_is_repeatable(
    engine: Engine,
) -> None:
    command.upgrade(_config(), "0012")
    _seed(engine)

    command.upgrade(_config(), "0013")

    expected = [
        (7, "C", True),  # two copies of one story, one derived row
        (7, "X", False),
        (7, "Y", False),
        (8, "C", False),  # the canonical's own mention stays real, no self-link
        (9, "unknown", False),  # not a source: no link
    ]
    assert _rows(engine) == expected
    with engine.connect() as conn:
        ingested = conn.execute(
            text(
                "SELECT ingested_at FROM mentions WHERE event_id = 7 AND url_hash = 'C'"
            )
        ).scalar_one()
    assert ingested.isoformat().startswith("2026-11-02T12:00")  # copied, not now()

    spec = importlib.util.spec_from_file_location("m0013", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:  # the backfill again: nothing new
        conn.execute(text(module.BACKFILL))
    assert _rows(engine) == expected


def test_orm_model_matches_migration_0013(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    assert [d for d in diff if "mentions" in str(d)] == []
