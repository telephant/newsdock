"""Push delivery (M2): subscriptions table and the articles NOTIFY trigger.

Forward-only, no data migration. The table is hand-written against
newsdock_db.models (autogenerate no-op test). The trigger is not part of the ORM
metadata: a statement-level AFTER INSERT with a transition table sends ONE
`articles_new` notification per insert statement, payload = max(seq) of the rows
that statement added; a statement that inserted nothing (ON CONFLICT DO NOTHING)
sends none. The notification is only a wake-up for SSE streams (ADR-0018).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column(
            "id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("filter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name="fk_subscriptions_agent_id_agents",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_subscriptions_agent_id", "subscriptions", ["agent_id"])
    op.execute("GRANT SELECT, INSERT, DELETE ON subscriptions TO api_rw")

    op.execute(
        """
        CREATE FUNCTION notify_articles_new() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE newest bigint;
        BEGIN
          SELECT max(seq) INTO newest FROM new_rows;
          IF newest IS NOT NULL THEN
            PERFORM pg_notify('articles_new', newest::text);
          END IF;
          RETURN NULL;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER articles_notify AFTER INSERT ON articles
        REFERENCING NEW TABLE AS new_rows
        FOR EACH STATEMENT EXECUTE FUNCTION notify_articles_new()
        """
    )


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
