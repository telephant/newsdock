"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from alembic import op

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
