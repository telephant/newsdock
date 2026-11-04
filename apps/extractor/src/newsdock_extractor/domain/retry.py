"""Which outcomes retry and when (design-detail.md sections 2 and 3, amended at T-01).

Transient: HTTP 429 (a request to slow down), 5xx, timeouts and connection errors.
They retry up to `max_attempts` with growing delays, then end as `failed`. Everything
else (other 4xx, not HTML, too large, no text, blocked) is final on the first try.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from newsdock_extractor.domain.status import BodyStatus

MAX_RETRY_WAIT = timedelta(hours=1)


@dataclass(frozen=True)
class NextState:
    status: BodyStatus  # `pending` while retries remain, else `failed`
    attempts: int
    next_attempt_at: datetime | None  # None when final
    host_delay_seconds: float | None = None  # raise the site's delay (429 only)


def is_transient_http(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def final_http_status(status_code: int) -> BodyStatus:
    """The final status of a non-transient HTTP error."""
    return BodyStatus.http_error


def after_transient_failure(
    *,
    attempts: int,
    now: datetime,
    backoff_minutes: Sequence[int],
    max_attempts: int,
    max_site_delay_seconds: float,
    retry_after_seconds: float | None = None,
) -> NextState:
    """The state after one more failed attempt (`attempts` is the count before it)."""
    count = attempts + 1
    host_delay = (
        min(retry_after_seconds, max_site_delay_seconds)
        if retry_after_seconds is not None
        else None
    )
    if count >= max_attempts:
        return NextState(BodyStatus.failed, count, None, host_delay)
    wait = timedelta(minutes=backoff_minutes[min(count - 1, len(backoff_minutes) - 1)])
    if retry_after_seconds is not None:
        wait = max(wait, min(timedelta(seconds=retry_after_seconds), MAX_RETRY_WAIT))
    return NextState(BodyStatus.pending, count, now + wait, host_delay)
