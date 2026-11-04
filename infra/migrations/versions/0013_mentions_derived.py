"""events-grouped-copies (M3e): derived mention rows link copies to the canonical.

Additive (DR-11), hand-written against newsdock_db.models. `mentions.derived` marks a
row the sink wrote for the canonical article because a copy of its story was mentioned
(ADR-0038); `mention_count` ignores those rows. The backfill adds the derived rows for
mentions already stored, with the copied `ingested_at` so retention removes both
together. Forward-only (DR-11).

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None

# the same statement the sink runs per batch (adapters/db.py), without a filter
BACKFILL = """
INSERT INTO mentions (event_id, url_hash, url, source_name, mention_time,
                      confidence, ingested_at, derived)
SELECT m.event_id, s.article_id, m.url, m.source_name, m.mention_time,
       m.confidence, m.ingested_at, true
FROM mentions m
JOIN article_sources s ON s.url_hash = m.url_hash
WHERE s.article_id <> m.url_hash AND NOT m.derived
ON CONFLICT (event_id, url_hash) DO NOTHING
"""


def upgrade() -> None:
    op.add_column(
        "mentions",
        sa.Column(
            "derived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    """Forward-only (DR-11): migrations are not rolled back."""
