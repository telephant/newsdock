"""semantic-search (M3), found at verify: a partial index for the embedder's queue.

The worker takes the newest articles without a vector. With only the `seq` index, the
filter "not embedded" made every pass walk past all the rows already embedded (measured
on 67,191 real articles: 1.8 ms with none embedded, ~100 ms at 60,000, and 78 ms for
every idle poll once all were embedded). This index holds only rows still waiting, so
the same query costs about 0.7 ms at any size, and it shrinks as the worker catches up.

Additive and forward-only (DR-11), hand-written against newsdock_db.models (the
autogenerate no-op test). No new grants: the worker only reads through it.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "ix_articles_unembedded",
        "articles",
        ["seq"],
        postgresql_where=sa.text("embedding IS NULL"),
    )


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
