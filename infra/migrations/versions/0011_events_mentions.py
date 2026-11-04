"""events-mentions (M3c): GDELT Events and Mentions, and per-file fetch state.

Additive and forward-only (DR-11), hand-written against newsdock_db.models (the
autogenerate no-op test). No foreign keys (ADR-0033, D-5): the files of a slot arrive in
any order, so a mention can precede its event and an event can precede its article;
the API joins on `url_hash` and `event_id`. `ingest_file` holds the fetch state of the
Events and Mentions file of a slot (ADR-0032); GKG stays in `ingest_slot`.

Grants: `sink_rw` writes and deletes events and mentions (retention), `api_rw` only
reads them, `ingester_rw` reads and writes `ingest_file` (no delete, as `ingest_slot`).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("event_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column(
            "is_root", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("actor1_code", sa.Text(), nullable=True),
        sa.Column("actor1_name", sa.Text(), nullable=True),
        sa.Column("actor1_country", sa.Text(), nullable=True),
        sa.Column("actor1_type", sa.Text(), nullable=True),
        sa.Column("actor2_code", sa.Text(), nullable=True),
        sa.Column("actor2_name", sa.Text(), nullable=True),
        sa.Column("actor2_country", sa.Text(), nullable=True),
        sa.Column("actor2_type", sa.Text(), nullable=True),
        sa.Column("cameo_code", sa.Text(), nullable=False),
        sa.Column("cameo_base", sa.Text(), nullable=True),
        sa.Column("cameo_root", sa.Text(), nullable=True),
        sa.Column("quad_class", sa.SmallInteger(), nullable=True),
        sa.Column("goldstein", postgresql.REAL(), nullable=True),
        sa.Column(
            "num_mentions", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "num_sources", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "num_articles", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("avg_tone", postgresql.REAL(), nullable=True),
        sa.Column("geo_name", sa.Text(), nullable=True),
        sa.Column("geo_country", sa.Text(), nullable=True),
        sa.Column("geo_adm1", sa.Text(), nullable=True),
        sa.Column("geo_lat", postgresql.DOUBLE_PRECISION(), nullable=True),
        sa.Column("geo_lon", postgresql.DOUBLE_PRECISION(), nullable=True),
        sa.Column("date_added", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_url_hash", sa.Text(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_events"),
    )
    op.create_index("ix_events_ingested_at", "events", ["ingested_at"])
    op.create_index("ix_events_source_url_hash", "events", ["source_url_hash"])

    op.create_table(
        "mentions",
        sa.Column("event_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("mention_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("event_id", "url_hash", name="pk_mentions"),
    )
    op.create_index("ix_mentions_url_hash", "mentions", ["url_hash", "event_id"])
    op.create_index("ix_mentions_ingested_at", "mentions", ["ingested_at"])

    op.create_table(
        "ingest_file",
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("slot", "kind", name="pk_ingest_file"),
        sa.CheckConstraint(
            "kind IN ('events', 'mentions')", name="ck_ingest_file_kind"
        ),
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON events TO sink_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON mentions TO sink_rw")
    op.execute("GRANT SELECT ON events TO api_rw")
    op.execute("GRANT SELECT ON mentions TO api_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE ON ingest_file TO ingester_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
