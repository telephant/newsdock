"""M1 tables: articles, analyses, ingest_slot, and the service roles.

Hand-written against newsdock_db.models (TC-34 proves no drift). The roles are
NOLOGIN group roles per design-detail §1; compose wires login users to them
(T-11). Idempotent role creation: a rerun on an already-migrated database is a
no-op because Alembic skips applied revisions.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REAL

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("gkg_record_id", sa.Text(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "themes",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "persons",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "orgs",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("tone", REAL(), nullable=True),
        sa.Column("tone_pos", REAL(), nullable=True),
        sa.Column("tone_neg", REAL(), nullable=True),
        sa.Column("tone_polarity", REAL(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("url_hash", name="pk_articles"),
        sa.UniqueConstraint("seq", name="uq_articles_seq"),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_index("ix_articles_ingested_at", "articles", ["ingested_at"])
    op.create_index(
        "ix_articles_themes", "articles", ["themes"], postgresql_using="gin"
    )
    op.create_index("ix_articles_domain", "articles", ["domain"])

    op.create_table(
        "analyses",
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("article_id", "agent_name", name="pk_analyses"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.url_hash"],
            name="fk_analyses_article_id_articles",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "ingest_slot",
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("slot", name="pk_ingest_slot"),
    )

    for role in ("ingester_rw", "sink_rw", "api_rw"):
        op.execute(
            f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
            END $$;"""
        )
    op.execute("GRANT SELECT, INSERT, UPDATE ON ingest_slot TO ingester_rw")
    op.execute("GRANT SELECT, INSERT, DELETE ON articles TO sink_rw")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sink_rw")
    op.execute("GRANT SELECT ON articles TO api_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE ON analyses TO api_rw")
    op.execute("GRANT SELECT ON ingest_slot TO api_rw")  # /api/health: last slot


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
