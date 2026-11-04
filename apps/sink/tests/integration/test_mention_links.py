"""TC-1, TC-2, TC-5, TC-6, TC-8, TC-10: derived mention rows from the sink (Docker).

A copy's mention gets a `derived` row for the canonical (ADR-0038), in both arrival
orders; a real mention of the canonical beats a derived one; replays change nothing;
retention removes both kinds. Throwaway Postgres from `side_db`, never the dev one.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_core.contracts import CleanMention
from newsdock_db.engine import make_engine
from newsdock_db.models import ArticleSource, Mention
from newsdock_db.testing import article
from newsdock_sink.adapters.db import SqlArticleWriter, SqlGdeltWriter
from newsdock_sink.domain.retention import cutoff
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
T0 = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def story(engine: Engine) -> None:
    """Canonical C with its own source and one copy X; Z is a second copy, unlinked."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE mentions"))
    with Session(engine) as session:
        session.add(article("C", "A story", domain="c.com"))
        session.commit()
        for key in ("C", "X"):
            session.add(_source(key, "C"))
        session.commit()


def _source(key: str, canonical: str) -> ArticleSource:
    return ArticleSource(
        url_hash=key, article_id=canonical, url=f"https://d.com/{key}",
        domain="d.com", slot="20261102110000", gkg_record_id="x", published_at=T0,
    )  # fmt: skip


def _mention(event_id: int, url_hash: str, minutes: int = 0) -> CleanMention:
    return CleanMention(
        event_id=event_id, url=f"https://d.com/{url_hash}", url_hash=url_hash,
        source_name="d.com", mention_time=T0 + timedelta(minutes=minutes),
        confidence=80,
    )  # fmt: skip


def _rows(engine: Engine) -> list[tuple[int, str, bool]]:
    with Session(engine) as session:
        found = session.execute(
            select(Mention.event_id, Mention.url_hash, Mention.derived).order_by(
                Mention.event_id, Mention.url_hash
            )
        ).all()
    return [(int(e), str(h), bool(d)) for e, h, d in found]


def test_a_mention_of_a_copy_gets_a_derived_row_for_the_canonical(
    engine: Engine,
) -> None:  # TC-1
    writer = SqlGdeltWriter(engine)
    batch = [_mention(7, "X"), _mention(8, "nobody")]

    writer.upsert_mentions(batch)
    writer.link_copy_mentions(batch)

    assert _rows(engine) == [(7, "C", True), (7, "X", False), (8, "nobody", False)]


def test_a_copy_grouped_after_its_mention_links_the_stored_mentions(
    engine: Engine,
) -> None:  # TC-2
    gdelt, articles = SqlGdeltWriter(engine), SqlArticleWriter(engine)
    with Session(engine) as session:
        session.add(_source("Z", "C"))
        session.commit()
    # the mention of Z arrived before Z was a copy: it was stored, with no link
    gdelt.upsert_mentions([_mention(9, "Z")])
    assert _rows(engine) == [(9, "Z", False)]

    articles.link_mentions_of("Z")

    assert _rows(engine) == [(9, "C", True), (9, "Z", False)]


def test_a_real_mention_of_the_canonical_beats_the_derived_row(
    engine: Engine,
) -> None:  # TC-5 (adapter half)
    writer = SqlGdeltWriter(engine)
    batch = [_mention(7, "X", minutes=30)]
    writer.upsert_mentions(batch)
    writer.link_copy_mentions(batch)
    assert (7, "C", True) in _rows(engine)

    writer.upsert_mentions([_mention(7, "C", minutes=0)])  # older than the derived row

    assert _rows(engine) == [(7, "C", False), (7, "X", False)]


def test_two_copies_and_the_canonical_make_one_row_per_event(
    engine: Engine,
) -> None:  # TC-6 (adapter half)
    with Session(engine) as session:
        session.add(_source("Z", "C"))
        session.commit()
    writer = SqlGdeltWriter(engine)
    batch = [_mention(7, "X"), _mention(7, "Z"), _mention(7, "C")]

    writer.upsert_mentions(batch)
    writer.link_copy_mentions(batch)

    assert _rows(engine) == [(7, "C", False), (7, "X", False), (7, "Z", False)]


def test_replaying_a_batch_changes_nothing(engine: Engine) -> None:  # TC-8
    writer = SqlGdeltWriter(engine)
    batch = [_mention(7, "X"), _mention(7, "C", minutes=5)]
    for _ in range(2):
        writer.upsert_mentions(batch)
        writer.link_copy_mentions(batch)
    once = _rows(engine)

    writer.upsert_mentions(batch)
    writer.link_copy_mentions(batch)
    SqlArticleWriter(engine).link_mentions_of("X")

    assert _rows(engine) == once == [(7, "C", False), (7, "X", False)]


def test_retention_removes_derived_and_real_rows_together(
    engine: Engine,
) -> None:  # TC-10
    writer = SqlGdeltWriter(engine)
    old, new = [_mention(1, "X")], [_mention(2, "X")]
    for batch in (old, new):
        writer.upsert_mentions(batch)
        writer.link_copy_mentions(batch)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE mentions SET ingested_at = :t WHERE event_id = 1"),
            {"t": datetime.now(UTC) - timedelta(days=8)},
        )

    writer.delete_ingested_before(cutoff(datetime.now(UTC), 7))

    assert _rows(engine) == [(2, "C", True), (2, "X", False)]
