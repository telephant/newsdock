"""Agent platform (M2): agents, api_keys, agent_cursors.

Forward-only, no data migration. Hand-written against newsdock_db.models; the
autogenerate no-op test (TC-34) proves no drift. Only the api role touches
these tables (ADR-0016, ADR-0017).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column(
            "id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agents"),
        sa.UniqueConstraint("name", name="uq_agents_name"),
    )
    op.create_table(
        "api_keys",
        sa.Column(
            "id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("prefix", name="uq_api_keys_prefix"),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name="fk_api_keys_agent_id_agents",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_api_keys_agent_id", "api_keys", ["agent_id"])
    op.create_table(
        "agent_cursors",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("agent_id", name="pk_agent_cursors"),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name="fk_agent_cursors_agent_id_agents",
            ondelete="CASCADE",
        ),
    )

    op.execute("GRANT SELECT, INSERT, UPDATE ON agents TO api_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE ON api_keys TO api_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE ON agent_cursors TO api_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
