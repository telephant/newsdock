"""semantic-search (M3): embedding columns, HNSW and full-text indexes on articles.

Additive and forward-only (DR-11), hand-written against newsdock_db.models (the
autogenerate no-op test). Both columns are nullable, so every existing row is
unchanged and the migration is metadata-only; the embedder worker fills them in
(ADR-0024, ADR-0025). The HNSW index (cosine, m 16, ef_construction 64) is built
on an all-NULL column, which is instant; NULLs are not indexed. The GIN index
serves the keyword leg of hybrid search (spec D-8). `embedder_rw` may read
articles and update only the two embedding columns.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("embedding", Vector(768), nullable=True))
    op.add_column("articles", sa.Column("embedding_model", sa.Text(), nullable=True))
    op.create_index(
        "ix_articles_embedding_hnsw",
        "articles",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_articles_title_fts",
        "articles",
        [sa.text("to_tsvector('english', title)")],
        postgresql_using="gin",
    )

    op.execute(
        """DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'embedder_rw') THEN
            CREATE ROLE embedder_rw NOLOGIN;
        END IF;
        END $$;"""
    )
    op.execute("GRANT SELECT ON articles TO embedder_rw")
    op.execute("GRANT UPDATE (embedding, embedding_model) ON articles TO embedder_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
