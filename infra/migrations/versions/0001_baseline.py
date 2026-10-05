"""baseline: make the pgvector extension available

Revision ID: 0001
Revises:
"""

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
