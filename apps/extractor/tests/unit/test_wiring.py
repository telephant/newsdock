"""The settings reach the worker and the fetcher unchanged."""

import pytest
from newsdock_extractor.adapters.fetch import FetchConfig
from newsdock_extractor.adapters.wiring import worker_config
from newsdock_extractor.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSDOCK_CONFIG_FILE", raising=False)


def test_worker_config_carries_every_setting() -> None:
    s = Settings(
        batch_size=11, concurrency=3, retention_days=5, backfill_hours=2, min_chars=77,
        text_cap_chars=999, passage_chars=500, passage_max_chars=600, max_attempts=4,
        retry_backoff_minutes="1,2,3", max_crawl_delay_seconds=12.5,
        robots_failure_minutes=7,
    )  # fmt: skip
    c = worker_config(s)
    assert (c.batch_size, c.concurrency, c.retention_days, c.backfill_hours) == (
        11,
        3,
        5,
        2,
    )
    assert (c.min_chars, c.text_cap_chars) == (77, 999)
    assert (c.passage_chars, c.passage_max_chars) == (500, 600)
    assert c.max_attempts == 4 and c.retry_backoff_minutes == (1, 2, 3)
    assert (c.max_crawl_delay_seconds, c.robots_failure_minutes) == (12.5, 7)


def test_fetch_config_carries_every_setting() -> None:
    s = Settings(
        user_agent="agent/1", connect_timeout_seconds=1.5, read_timeout_seconds=2.5,
        total_timeout_seconds=9.0, max_bytes=1234, max_redirects=2,
        max_crawl_delay_seconds=20.0, robots_ttl_hours=3, robots_failure_minutes=4,
    )  # fmt: skip
    assert FetchConfig.from_settings(s) == FetchConfig(
        user_agent="agent/1", connect_timeout_seconds=1.5, read_timeout_seconds=2.5,
        total_timeout_seconds=9.0, max_bytes=1234, max_redirects=2,
        max_crawl_delay_seconds=20.0, robots_ttl_hours=3, robots_failure_minutes=4,
    )  # fmt: skip


def test_the_defaults_describe_a_polite_worker() -> None:
    c = worker_config(Settings())
    assert c.concurrency == 16 and c.max_attempts == 3
    assert c.retry_backoff_minutes == (5, 30)
    assert (
        Settings().db_backoff_seconds == 5.0
        and Settings().db_backoff_max_seconds == 60.0
    )
