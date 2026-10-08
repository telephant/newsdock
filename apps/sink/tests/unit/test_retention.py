"""TC-13: the cutoff comes from the injected clock (R-10) and configured days."""

from datetime import UTC, datetime, timedelta

from newsdock_sink.config import Settings
from newsdock_sink.domain.retention import cutoff

NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)


def test_cutoff_is_the_configured_days_before_the_injected_now() -> None:
    assert cutoff(NOW, retention_days=3) == NOW - timedelta(days=3)
    assert cutoff(NOW, retention_days=7) == NOW - timedelta(days=7)


def test_default_retention_is_seven_days() -> None:
    assert Settings().retention_days == 7
