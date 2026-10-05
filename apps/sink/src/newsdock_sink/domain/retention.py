"""Retention decision: 7 days on ingested_at, clock injected (AC-7, R-10)."""

from datetime import datetime, timedelta

RETENTION_DAYS = 7


def cutoff(now: datetime) -> datetime:
    return now - timedelta(days=RETENTION_DAYS)
