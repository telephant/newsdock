"""TC-13 (decision half): the cutoff comes from the injected clock (R-10)."""

from datetime import UTC, datetime, timedelta

from newsdock_sink.domain.retention import RETENTION_DAYS, cutoff


def test_cutoff_is_seven_days_before_the_injected_now() -> None:
    now = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
    assert RETENTION_DAYS == 7
    assert cutoff(now) == now - timedelta(days=7)
