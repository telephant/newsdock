"""Retention decision: N days on ingested_at, clock injected (AC-7, R-10)."""

from datetime import datetime, timedelta


def cutoff(now: datetime, retention_days: int) -> datetime:
    return now - timedelta(days=retention_days)
