"""ui-login (M2): human accounts and login sessions.

Forward-only, no data migration. Hand-written against newsdock_db.models (the
autogenerate no-op test). `users.email` is stored lower-cased by the application;
`sessions.token_hash` is the sha256 of the cookie value (ADR-0020). The API role
may read and write both tables; nothing else touches them.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'viewer')", name="ck_users_role"
        ),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sessions_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON users TO api_rw")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO api_rw")


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
