"""Which queue rows are due, newest first (D-6, ADR-0036).

These pure functions state the rule; the database adapter applies the same rule in SQL
(`WHERE status = 'pending' AND next_attempt_at <= now AND created_at >= window ORDER BY
seq DESC LIMIT n`) and the tests hold both to it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class QueueRow:
    url_hash: str
    url: str
    seq: int
    created_at: datetime
    next_attempt_at: datetime
    attempts: int


def window_start(now: datetime, *, retention_days: int) -> datetime:
    """Articles created before this are never fetched (older than the 7-day window)."""
    return now - timedelta(days=retention_days)


def eligible(
    rows: Sequence[QueueRow],
    now: datetime,
    *,
    retention_days: int,
    limit: int | None = None,
) -> list[QueueRow]:
    """The rows to work on: due, inside the window, newest first, at most `limit`."""
    start = window_start(now, retention_days=retention_days)
    due = [r for r in rows if r.next_attempt_at <= now and r.created_at >= start]
    due.sort(key=lambda r: r.seq, reverse=True)
    return due if limit is None else due[:limit]
