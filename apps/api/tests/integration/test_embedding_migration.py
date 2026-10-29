"""TC-1 (AC-1): migration 0008 adds the embedding columns and indexes (Docker).

Migrations are forward-only (DR-11), so there is no downgrade case.
"""

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
OLD_COLUMNS = (
    "url_hash, story_key, seq, gkg_record_id, slot, url, title, domain, published_at, "
    "ingested_at, themes, persons, orgs, tone, tone_pos, tone_neg, tone_polarity, "
    "word_count"
)


def _config() -> Config:
    return Config(str(ROOT / "infra" / "migrations" / "alembic.ini"))


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def _insert_old_articles(engine: Engine) -> None:
    with engine.begin() as conn:
        for key in ("a1", "a2", "a3"):
            conn.execute(
                text(
                    "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                    "domain, published_at, themes) VALUES (:k, 'r', '20261028120000', "
                    ":u, :t, 'example.com', now(), ARRAY['ECON_X'])"
                ),
                {"k": key, "u": f"https://example.com/{key}", "t": f"Title {key}"},
            )


def _snapshot(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {OLD_COLUMNS} FROM articles ORDER BY url_hash")
        ).all()
    return [tuple(row) for row in rows]


def test_migration_adds_columns_indexes_and_keeps_rows(engine: Engine) -> None:
    command.upgrade(_config(), "0007")
    _insert_old_articles(engine)
    before = _snapshot(engine)
    assert len(before) == 3

    command.upgrade(_config(), "0008")

    with engine.connect() as conn:
        columns = {
            name: (kind, notnull)
            for name, kind, notnull in conn.execute(
                text(
                    "SELECT attname, format_type(atttypid, atttypmod), attnotnull "
                    "FROM pg_attribute WHERE attrelid = 'articles'::regclass "
                    "AND attname IN ('embedding', 'embedding_model')"
                )
            )
        }
        indexes: dict[str, str] = dict(
            conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'articles' AND indexname IN "
                    "('ix_articles_embedding_hnsw', 'ix_articles_title_fts')"
                )
            ).all()
        )
        embedded = conn.execute(
            text("SELECT count(*) FROM articles WHERE embedding IS NOT NULL")
        ).scalar_one()

    assert columns == {
        "embedding": ("vector(768)", False),
        "embedding_model": ("text", False),
    }
    hnsw = indexes["ix_articles_embedding_hnsw"]
    assert "USING hnsw" in hnsw and "vector_cosine_ops" in hnsw
    assert "m='16'" in hnsw.replace(" ", "") or "m=16" in hnsw.replace(" ", "")
    fts = indexes["ix_articles_title_fts"]
    assert "USING gin" in fts and "to_tsvector('english'" in fts
    assert embedded == 0
    assert _snapshot(engine) == before  # every old row and column is unchanged

    command.upgrade(_config(), "head")  # idempotent


def test_embedder_role_may_update_only_the_embedding_columns(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:

        def can(privilege: str, column: str | None) -> bool:
            if column is None:
                sql = "SELECT has_table_privilege('embedder_rw', 'articles', :p)"
            else:
                sql = (
                    "SELECT has_column_privilege('embedder_rw', 'articles', "
                    f"'{column}', :p)"
                )
            return bool(conn.execute(text(sql), {"p": privilege}).scalar_one())

        assert can("SELECT", None)
        assert can("UPDATE", "embedding")
        assert can("UPDATE", "embedding_model")
        assert not can("UPDATE", "title")
        assert not can("INSERT", None)
        assert not can("DELETE", None)


def test_model_matches_migration(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), metadata)
    assert diff == [], f"schema drift between models and migrations: {diff}"


def test_migration_0009_adds_the_partial_queue_index(engine: Engine) -> None:
    command.upgrade(_config(), "head")
    with engine.connect() as conn:
        definition = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'articles' "
                "AND indexname = 'ix_articles_unembedded'"
            )
        ).scalar_one()
        version = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert "(seq)" in definition and "WHERE (embedding IS NULL)" in definition
    assert version >= "0009"  # revision ids are zero-padded, so later heads still pass
