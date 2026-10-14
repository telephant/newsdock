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
