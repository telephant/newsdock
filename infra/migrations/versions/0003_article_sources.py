"""Story dedup (M2a): articles.story_key and the article_sources table.

Forward-only, NO backfill (spec D-4): existing rows keep story_key NULL and
never group; the 7-day retention converges the store. Hand-written against
newsdock_db.models; the autogenerate no-op test proves no drift.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("story_key", sa.Text(), nullable=True))
    op.create_index(
        "ix_articles_story_key_published_at",
        "articles",
        ["story_key", "published_at"],
    )

    op.create_table(
        "article_sources",
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("gkg_record_id", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("url_hash", name="pk_article_sources"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.url_hash"],
            name="fk_article_sources_article_id_articles",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_article_sources_article_id", "article_sources", ["article_id"])

    op.execute("GRANT SELECT, INSERT, DELETE ON article_sources TO sink_rw")
    op.execute("GRANT SELECT ON article_sources TO api_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
