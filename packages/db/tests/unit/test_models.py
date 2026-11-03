"""M1 tables are registered on the shared metadata with the designed names."""

from newsdock_db import models
from newsdock_db.metadata import metadata


def test_designed_tables_are_registered() -> None:
    assert {"articles", "analyses", "ingest_slot"} <= set(metadata.tables)


def test_articles_contract() -> None:
    articles = metadata.tables["articles"]
    assert [c.name for c in articles.primary_key.columns] == ["url_hash"]
    assert articles.c.seq.unique
    assert not articles.c.published_at.nullable
    assert articles.c.domain.nullable
    assert models.Article.__tablename__ == "articles"


def test_analyses_composite_pk_and_cascade() -> None:
    analyses = metadata.tables["analyses"]
    assert [c.name for c in analyses.primary_key.columns] == [
        "article_id",
        "agent_name",
    ]
    (fk,) = analyses.c.article_id.foreign_keys
    assert fk.ondelete == "CASCADE"
    assert fk.column.table.name == "articles"


def test_ingest_slot_contract() -> None:
    slot = metadata.tables["ingest_slot"]
    assert [c.name for c in slot.primary_key.columns] == ["slot"]
    assert not slot.c.status.nullable
    assert models.IngestSlot.__tablename__ == "ingest_slot"


def test_agent_platform_tables_contract() -> None:
    agents = metadata.tables["agents"]
    assert agents.c.name.unique
    keys = metadata.tables["api_keys"]
    assert keys.c.prefix.unique
    assert "key_hash" in keys.c and "secret" not in keys.c  # never the plaintext
    (fk,) = keys.c.agent_id.foreign_keys
    assert fk.ondelete == "CASCADE" and fk.column.table.name == "agents"
    cursors = metadata.tables["agent_cursors"]
    assert [c.name for c in cursors.primary_key.columns] == ["agent_id"]


def test_subscriptions_table_contract() -> None:
    subs = metadata.tables["subscriptions"]
    (fk,) = subs.c.agent_id.foreign_keys
    assert fk.ondelete == "CASCADE" and fk.column.table.name == "agents"
    assert str(subs.c.filter.type) == "JSONB"


def test_events_mentions_tables_contract() -> None:
    """TC-22 (events-mentions, ADR-0033): keys, no foreign keys, join indexes."""
    events = metadata.tables["events"]
    assert [c.name for c in events.primary_key.columns] == ["event_id"]
    assert not events.c.event_date.nullable and not events.c.date_added.nullable
    assert not events.c.source_url.nullable and not events.c.source_url_hash.nullable
    assert not events.foreign_keys  # D-5: no foreign key, rows arrive in any order
    assert {i.name for i in events.indexes} == {
        "ix_events_ingested_at",
        "ix_events_source_url_hash",
    }
    mentions = metadata.tables["mentions"]
    assert [c.name for c in mentions.primary_key.columns] == ["event_id", "url_hash"]
    assert not mentions.foreign_keys
    assert not mentions.c.mention_time.nullable and mentions.c.confidence.nullable
    assert {i.name for i in mentions.indexes} == {
        "ix_mentions_url_hash",
        "ix_mentions_ingested_at",
    }
    assert models.Event.__tablename__ == "events"
    assert models.Mention.__tablename__ == "mentions"


def test_ingest_file_contract() -> None:
    files = metadata.tables["ingest_file"]
    assert [c.name for c in files.primary_key.columns] == ["slot", "kind"]
    assert not files.c.status.nullable
    assert models.IngestFile.__tablename__ == "ingest_file"


def test_article_bodies_contract() -> None:
    """TC-27 (body-extraction, ADR-0036): the queue and the text of a body."""
    bodies = metadata.tables["article_bodies"]
    assert [c.name for c in bodies.primary_key.columns] == ["url_hash"]
    (fk,) = bodies.c.url_hash.foreign_keys
    assert fk.ondelete == "CASCADE" and fk.column.table.name == "articles"
    assert not bodies.c.seq.nullable and not bodies.c.status.nullable
    assert bodies.c.text.nullable and bodies.c.http_status.nullable
    assert {i.name for i in bodies.indexes} == {
        "ix_article_bodies_seq",
        "ix_article_bodies_pending",
    }
    pending = next(i for i in bodies.indexes if i.name == "ix_article_bodies_pending")
    assert "status = 'pending'" in str(pending.dialect_options["postgresql"]["where"])
    assert models.ArticleBody.__tablename__ == "article_bodies"


def test_article_passages_contract() -> None:
    passages = metadata.tables["article_passages"]
    assert [c.name for c in passages.primary_key.columns] == ["url_hash", "idx"]
    (fk,) = passages.c.url_hash.foreign_keys
    assert fk.ondelete == "CASCADE" and fk.column.table.name == "articles"
    assert not passages.c.text.nullable
    assert passages.c.embedding.nullable and passages.c.embedding_model.nullable
    assert type(passages.c.embedding.type).__name__ == "HALFVEC"
    assert {i.name for i in passages.indexes} == {
        "ix_article_passages_embedding_hnsw",
        "ix_article_passages_text_fts",
        "ix_article_passages_unembedded",
    }
    assert models.ArticlePassage.__tablename__ == "article_passages"
