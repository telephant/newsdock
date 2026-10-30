"""forgot-password (M2f): one open reset code per user.

Additive and forward-only (DR-11), hand-written against newsdock_db.models (the
autogenerate no-op test). `user_id` is the primary key, so a newer request replaces
the older code with an upsert; deleting the user removes the row. `code_hash` is a keyed
HMAC of the code, never the code itself (ADR-0026). `api_rw` owns all reads and writes.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_password_resets"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_password_resets_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON password_resets TO api_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
