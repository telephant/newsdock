"""TC-13 (AC-8): retention covers events and mentions and leaves articles' rule alone.

Runs against a throwaway Postgres from the `side_db` fixture (own compose project),
so the dev stack's database is never touched.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_core.contracts import CleanEvent, CleanMention
from newsdock_core.events import parse_event_row
from newsdock_core.mentions import parse_mention_row
from newsdock_db.engine import make_engine
from newsdock_db.models import Article, Event, Mention
from newsdock_sink.adapters.db import SqlArticleWriter, SqlGdeltWriter
from newsdock_sink.domain.retention import cutoff
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def _events(count: int) -> list[CleanEvent]:
    lines = (FIXTURES / "events_sample.tsv").read_text().splitlines()[:count]
    parsed = [parse_event_row(slot="s", row_no=n, line=x) for n, x in enumerate(lines)]
    assert all(isinstance(p, CleanEvent) for p in parsed)
    return [p for p in parsed if isinstance(p, CleanEvent)]


def _mentions() -> list[CleanMention]:
    lines = (FIXTURES / "mentions_sample.tsv").read_text().splitlines()
    out: list[CleanMention] = []
    seen: set[tuple[int, str]] = set()
    for n, line in enumerate(lines):
        parsed = parse_mention_row(slot="s", row_no=n, line=line)
        assert isinstance(parsed, CleanMention)
        if (parsed.event_id, parsed.url_hash) not in seen:
            seen.add((parsed.event_id, parsed.url_hash))
            out.append(parsed)
    return out


def _age(engine: Engine, table: str, key_sql: str, keys: list[str], days: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE {table} SET ingested_at = :t WHERE {key_sql} = ANY(:keys)"),
            {"t": NOW - timedelta(days=days), "keys": keys},
        )


def test_retention_deletes_old_events_and_mentions_and_keeps_fresh_ones(
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE events, mentions"))
        conn.execute(text("TRUNCATE articles CASCADE"))
    gdelt = SqlGdeltWriter(engine)
    events, mentions = _events(4), _mentions()[:6]
    gdelt.upsert_events(events)
    gdelt.upsert_mentions(mentions)
    old_events = [str(e.event_id) for e in events[:2]]
    old_hashes = [m.url_hash for m in mentions[:3]]
    _age(engine, "events", "event_id::text", old_events, 8)
    _age(engine, "events", "event_id::text", [str(e.event_id) for e in events[2:]], 6)
    _age(engine, "mentions", "url_hash", old_hashes, 8)
    with Session(engine) as session:
        session.add(
            Article(
                url_hash="old-article", gkg_record_id="x", slot="s", url="https://e/a",
                title="old", domain=None, published_at=NOW,
                ingested_at=NOW - timedelta(days=8), themes=[], persons=[], orgs=[],
            )
        )  # fmt: skip
        session.commit()
    with Session(engine) as session:
        old_mentions = session.scalars(
            select(Mention).where(Mention.ingested_at < NOW - timedelta(days=7))
        ).all()
    assert old_mentions  # the setup really aged some mentions

    limit = cutoff(NOW, 7)
    articles_deleted = SqlArticleWriter(engine).delete_ingested_before(limit)
    events_deleted, mentions_deleted = gdelt.delete_ingested_before(limit)

    assert articles_deleted == 1  # the articles rule is unchanged
    assert events_deleted == 2
    assert mentions_deleted == len(old_mentions)
    with Session(engine) as session:
        kept_events = {e.event_id for e in session.scalars(select(Event))}
        kept_mentions = session.scalars(select(Mention)).all()
    assert kept_events == {e.event_id for e in events[2:]}
    assert all(m.ingested_at >= limit for m in kept_mentions)
    assert len(kept_mentions) == len(mentions) - mentions_deleted


def test_retention_with_nothing_old_deletes_nothing(engine: Engine) -> None:
    gdelt = SqlGdeltWriter(engine)
    assert gdelt.delete_ingested_before(cutoff(NOW - timedelta(days=30), 7)) == (0, 0)
