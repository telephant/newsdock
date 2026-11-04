"""body-extraction (M3d): article bodies (the extractor's queue) and embedded passages.

Additive and forward-only (DR-11), hand-written against newsdock_db.models (the
autogenerate no-op test). `article_bodies` holds one row per canonical article: the
extractor creates it `pending`, then stores the fetched text with a status; its partial
index is the queue, read newest first (ADR-0036). `article_passages` holds the pieces of
a body with a `halfvec(768)` vector filled by the embedder (half the storage of
`vector(768)`, measured in T-01: 4.9 KB against 9.4 KB per passage with indexes).
Both tables cascade from `articles`, so the sink's retention delete removes them.
The HNSW index is built on an empty table, which is instant.

Roles: `extractor_rw` (new, NOLOGIN like the others) reads articles, reads, inserts
and updates bodies, reads and inserts passages; `embedder_rw` reads passages and
updates only the two embedding columns; `api_rw` reads both tables.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "article_bodies",
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column(
            "attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("url_hash", name="pk_article_bodies"),
        sa.ForeignKeyConstraint(
            ["url_hash"],
            ["articles.url_hash"],
            name="fk_article_bodies_url_hash_articles",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ok', 'blocked_robots', 'blocked_address', "
            "'http_error', 'not_html', 'too_large', 'no_text', 'failed')",
            name="ck_article_bodies_status",
        ),
    )
    op.create_index("ix_article_bodies_seq", "article_bodies", ["seq"])
    op.create_index(
        "ix_article_bodies_pending",
        "article_bodies",
        ["seq"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "article_passages",
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("idx", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", HALFVEC(768), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("url_hash", "idx", name="pk_article_passages"),
        sa.ForeignKeyConstraint(
            ["url_hash"],
            ["articles.url_hash"],
            name="fk_article_passages_url_hash_articles",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_article_passages_embedding_hnsw",
        "article_passages",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )
    op.create_index(
        "ix_article_passages_text_fts",
        "article_passages",
        [sa.text("to_tsvector('english', text)")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_article_passages_unembedded",
        "article_passages",
        ["url_hash"],
        postgresql_where=sa.text("embedding IS NULL"),
    )

    op.execute(
        """DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'extractor_rw') THEN
            CREATE ROLE extractor_rw NOLOGIN;
        END IF;
        END $$;"""
    )
    op.execute("GRANT SELECT ON articles TO extractor_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE ON article_bodies TO extractor_rw")
    op.execute("GRANT SELECT, INSERT ON article_passages TO extractor_rw")
    op.execute("GRANT SELECT ON article_passages TO embedder_rw")
    op.execute(
        "GRANT UPDATE (embedding, embedding_model) ON article_passages TO embedder_rw"
    )
    op.execute("GRANT SELECT ON article_bodies TO api_rw")
    op.execute("GRANT SELECT ON article_passages TO api_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
