"""TC-34 + TC-14: migrations match the ORM metadata; cascade works (needs Docker).

Runs against a throwaway Postgres from the `side_db` fixture (own compose project,
free port), so a real dev stack is never touched.
"""

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
from newsdock_db.models import (
    Analysis,
    Article,
    ArticleBody,
    ArticlePassage,
    Event,
    IngestFile,
    IngestSlot,
    Mention,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture()
def migrated_url(side_db: tuple[str, str]) -> Iterator[str]:
    database_url = side_db[0]
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


def _can(session: Session, role: str, table: str, privilege: str) -> bool:
    return bool(
        session.execute(
            text("SELECT has_table_privilege(:role, :table, :privilege)"),
            {"role": role, "table": table, "privilege": privilege},
        ).scalar_one()
    )


# TC-22: events, mentions and ingest_file exist, round-trip and have the right keys
def test_events_mentions_roundtrip_and_keys(migrated_url: str) -> None:
    now = datetime.now(UTC)
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        session.add(
            Event(
                event_id=1331041275, event_date=now.date(), is_root=False,
                cameo_code="040", goldstein=1.0, num_mentions=5, num_sources=1,
                num_articles=5, avg_tone=-2.7, geo_lat=38.762, geo_lon=-90.1171,
                date_added=now, source_url="https://example.com/a",
                source_url_hash="h1",
            )
        )  # fmt: skip
        session.add_all([
            Mention(event_id=1331041275, url_hash="h1", url="https://example.com/a",
                    mention_time=now, confidence=20),
            Mention(event_id=1331041275, url_hash="h2", url="https://example.com/b",
                    mention_time=now),
            Mention(event_id=999, url_hash="h1", url="https://example.com/a",
                    mention_time=now),  # event we never stored: no foreign key
        ])  # fmt: skip
        session.commit()
        stored = session.get(Event, 1331041275)
        assert stored is not None and stored.ingested_at is not None
        assert session.query(Mention).count() == 3
        session.add(
            Mention(event_id=1331041275, url_hash="h1", url="https://example.com/a",
                    mention_time=now)
        )  # fmt: skip
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(IngestFile(slot="20261102110000", kind="events", status="pending"))
        session.commit()
        file_row = session.get(IngestFile, ("20261102110000", "events"))
        assert file_row is not None and file_row.attempts == 0
        session.add(IngestFile(slot="20261102110000", kind="gkg", status="pending"))
        with pytest.raises(IntegrityError):
            session.commit()  # only events and mentions live in ingest_file
        session.rollback()
        session.execute(text("DELETE FROM mentions"))
        session.execute(text("DELETE FROM events"))
        session.execute(text("DELETE FROM ingest_file"))
        session.commit()
    engine.dispose()


def test_events_mentions_grants(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        for table in ("events", "mentions"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert _can(session, "sink_rw", table, privilege), (table, privilege)
            assert _can(session, "api_rw", table, "SELECT")
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert not _can(session, "api_rw", table, privilege), (table, privilege)
            assert not _can(session, "ingester_rw", table, "SELECT")
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            assert _can(session, "ingester_rw", "ingest_file", privilege)
        assert not _can(session, "ingester_rw", "ingest_file", "DELETE")
        assert not _can(session, "sink_rw", "ingest_file", "INSERT")
    engine.dispose()


# TC-27 (body-extraction): bodies and passages, cascade, status check, indexes, grants
def test_bodies_and_passages_cascade_with_the_article(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        session.add(_article("b1"))
        session.add(_article("b2"))
        session.commit()
        session.add_all([
            ArticleBody(url_hash="b1", seq=1, status="ok", text="body one"),
            ArticleBody(url_hash="b2", seq=2),
            ArticlePassage(url_hash="b1", idx=0, text="first", embedding=[0.5] * 768,
                           embedding_model="m"),
            ArticlePassage(url_hash="b1", idx=1, text="second"),
        ])  # fmt: skip
        session.commit()
        pending = session.get(ArticleBody, "b2")
        assert pending is not None and pending.status == "pending"
        assert pending.attempts == 0 and pending.next_attempt_at is not None
        passage = session.get(ArticlePassage, ("b1", 0))
        assert passage is not None and passage.embedding is not None
        assert len(passage.embedding) == 768
        session.delete(session.get(Article, "b1"))
        session.commit()
        assert session.get(ArticleBody, "b1") is None
        assert session.get(ArticlePassage, ("b1", 0)) is None
        assert session.get(ArticlePassage, ("b1", 1)) is None
        assert session.get(ArticleBody, "b2") is not None  # other articles untouched
        session.delete(session.get(Article, "b2"))
        session.commit()
    engine.dispose()


def test_an_unknown_body_status_is_rejected(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        session.add(_article("b3"))
        session.commit()
        session.add(ArticleBody(url_hash="b3", seq=3, status="bogus"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        for status in (
            "pending",
            "ok",
            "blocked_robots",
            "blocked_address",
            "http_error",
            "not_html",
            "too_large",
            "no_text",
            "failed",
        ):
            session.merge(ArticleBody(url_hash="b3", seq=3, status=status))
            session.commit()
        session.delete(session.get(Article, "b3"))
        session.commit()
    engine.dispose()


def test_passage_indexes_use_halfvec_hnsw_and_the_partial_queue(
    migrated_url: str,
) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN "
                "('article_bodies', 'article_passages')"
            )
        ).all()
        defs = {name: definition for name, definition in rows}
        column = session.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'article_passages'::regclass "
                "AND attname = 'embedding'"
            )
        ).scalar_one()
    engine.dispose()
    assert column == "halfvec(768)"
    assert "USING hnsw" in defs["ix_article_passages_embedding_hnsw"]
    assert "halfvec_cosine_ops" in defs["ix_article_passages_embedding_hnsw"]
    assert "m='16'" in defs["ix_article_passages_embedding_hnsw"]
    assert "USING gin" in defs["ix_article_passages_text_fts"]
    assert "WHERE (embedding IS NULL)" in defs["ix_article_passages_unembedded"]
    assert "WHERE (status = 'pending'::text)" in defs["ix_article_bodies_pending"]
    assert "ix_article_bodies_seq" in defs


def test_body_and_passage_grants(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    with Session(engine) as session:
        roles = session.execute(
            text("SELECT rolname FROM pg_roles WHERE rolname = 'extractor_rw'")
        ).scalars().all()  # fmt: skip
        assert roles == ["extractor_rw"]
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            assert _can(session, "extractor_rw", "article_bodies", privilege)
        assert not _can(session, "extractor_rw", "article_bodies", "DELETE")
        assert _can(session, "extractor_rw", "article_passages", "SELECT")
        assert _can(session, "extractor_rw", "article_passages", "INSERT")
        assert not _can(session, "extractor_rw", "article_passages", "UPDATE")
        assert _can(session, "extractor_rw", "articles", "SELECT")
        assert not _can(session, "extractor_rw", "articles", "UPDATE")
        assert _can(session, "embedder_rw", "article_passages", "SELECT")
        assert not _can(session, "embedder_rw", "article_passages", "INSERT")
        assert not _can(session, "embedder_rw", "article_passages", "DELETE")
        column_update = session.execute(
            text(
                "SELECT has_column_privilege('embedder_rw', 'article_passages', "
                "'embedding', 'UPDATE')"
            )
        ).scalar_one()
        text_update = session.execute(
            text(
                "SELECT has_column_privilege('embedder_rw', 'article_passages', "
                "'text', 'UPDATE')"
            )
        ).scalar_one()
        assert column_update and not text_update
        for table in ("article_bodies", "article_passages"):
            assert _can(session, "api_rw", table, "SELECT")
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert not _can(session, "api_rw", table, privilege)
    engine.dispose()
