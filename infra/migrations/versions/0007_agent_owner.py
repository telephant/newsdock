"""agent-ownership (M2d): every agent may record the user who created it.

Additive and forward-only (DR-11), hand-written against newsdock_db.models (the
autogenerate no-op test). `agents.owner_id` is NULL for existing agents, for agents
made by the CLI or the admin token, and for agents whose creator was deleted
(`ON DELETE SET NULL`): they keep working, and only the owner role and the admin
token can manage them (ADR-0023). The api_rw grants on `agents` already cover it.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agents_owner_id_users",
        "agents",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agents_owner_id", "agents", ["owner_id"])


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
