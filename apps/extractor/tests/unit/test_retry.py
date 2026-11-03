"""TC-12 (AC-5): which outcomes retry, and when; every other outcome is final."""

from datetime import UTC, datetime, timedelta

import pytest
from newsdock_extractor.domain.retry import (
    after_transient_failure,
    final_http_status,
    is_transient_http,
)
from newsdock_extractor.domain.status import BodyStatus

NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
BACKOFF = (5, 30)


@pytest.mark.parametrize(
    ("status", "transient"),
    [
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (599, True),
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (410, False),
        (451, False),
        (499, False),
    ],
)
def test_only_429_and_5xx_are_transient(status: int, transient: bool) -> None:
    assert is_transient_http(status) is transient


def test_a_final_http_failure_is_http_error() -> None:
    assert final_http_status(403) is BodyStatus.http_error
    assert final_http_status(451) is BodyStatus.http_error


def test_the_first_failure_waits_five_minutes_and_stays_pending() -> None:
    state = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0,
    )  # fmt: skip
    assert state.status is BodyStatus.pending
    assert state.attempts == 1
    assert state.next_attempt_at == NOW + timedelta(minutes=5)


def test_the_second_failure_waits_thirty_minutes() -> None:
    state = after_transient_failure(
        attempts=1, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0,
    )  # fmt: skip
    assert (state.status, state.attempts) == (BodyStatus.pending, 2)
    assert state.next_attempt_at == NOW + timedelta(minutes=30)


def test_the_third_failure_is_final() -> None:
    state = after_transient_failure(
        attempts=2, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0,
    )  # fmt: skip
    assert state.status is BodyStatus.failed
    assert state.attempts == 3
    assert state.next_attempt_at is None


def test_a_short_backoff_list_repeats_its_last_value() -> None:
    state = after_transient_failure(
        attempts=3, now=NOW, backoff_minutes=(10,), max_attempts=9,
        max_site_delay_seconds=30.0,
    )  # fmt: skip
    assert state.next_attempt_at == NOW + timedelta(minutes=10)


def test_a_retry_after_longer_than_the_backoff_wins_but_is_capped_at_an_hour() -> None:
    long = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0, retry_after_seconds=20 * 60,
    )  # fmt: skip
    assert long.next_attempt_at == NOW + timedelta(minutes=20)
    huge = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0, retry_after_seconds=48 * 3600,
    )  # fmt: skip
    assert huge.next_attempt_at == NOW + timedelta(hours=1)
    short = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0, retry_after_seconds=10,
    )  # fmt: skip
    assert short.next_attempt_at == NOW + timedelta(minutes=5)  # the backoff is longer


def test_a_retry_after_raises_the_delay_of_the_whole_site_up_to_the_cap() -> None:
    asked = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0, retry_after_seconds=12,
    )  # fmt: skip
    assert asked.host_delay_seconds == 12.0
    capped = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0, retry_after_seconds=600,
    )  # fmt: skip
    assert capped.host_delay_seconds == 30.0
    plain = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=3,
        max_site_delay_seconds=30.0,
    )  # fmt: skip
    assert plain.host_delay_seconds is None  # a 5xx does not change the site's delay


def test_max_attempts_of_one_means_no_retry_at_all() -> None:
    state = after_transient_failure(
        attempts=0, now=NOW, backoff_minutes=BACKOFF, max_attempts=1,
        max_site_delay_seconds=30.0,
    )  # fmt: skip
    assert (state.status, state.attempts) == (BodyStatus.failed, 1)
