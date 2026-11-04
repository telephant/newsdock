"""TC-28: extractor settings from the code defaults, the file and the environment."""

from pathlib import Path

import pytest
from newsdock_extractor.config import Settings

ENV_NAMES = (
    "NEWSDOCK_CONFIG_FILE",
    "NEWSDOCK_LOG_LEVEL",
    "NEWSDOCK_CONCURRENCY",
    "NEWSDOCK_PER_HOST_DELAY_SECONDS",
    "NEWSDOCK_USER_AGENT",
    "NEWSDOCK_RETRY_BACKOFF_MINUTES",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))


def test_defaults_are_the_designed_values() -> None:
    """design-detail.md section 8: provisional numbers, decisions marked."""
    s = Settings()
    assert (s.poll_interval_seconds, s.batch_size, s.concurrency) == (5.0, 200, 16)
    assert s.backfill_hours == 6
    assert (s.per_host_delay_seconds, s.max_crawl_delay_seconds) == (5.0, 30.0)
    assert (s.robots_ttl_hours, s.robots_failure_minutes) == (24, 60)
    assert (s.connect_timeout_seconds, s.read_timeout_seconds) == (5.0, 15.0)
    assert s.total_timeout_seconds == 20.0
    assert (s.max_bytes, s.max_redirects) == (2_000_000, 3)
    assert (s.min_chars, s.text_cap_chars) == (200, 20_000)  # the cap is a decision
    assert (s.passage_chars, s.passage_max_chars) == (1000, 1200)
    assert s.max_attempts == 3
    assert s.retry_backoff() == (5, 30)
    assert s.retention_days == 7  # a decision (D-3)
    assert s.heartbeat_file == "/tmp/healthy"
    assert s.heartbeat_max_age_seconds == 300
    assert s.log_level == "INFO"


def test_user_agent_is_descriptive_and_says_it_obeys_robots() -> None:
    agent = Settings().user_agent
    assert agent.startswith("newsdock-extractor/")
    assert "robots.txt" in agent


def test_file_overrides_defaults_and_env_overrides_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "extractor:\n  concurrency: 8\n  per_host_delay_seconds: 7\n",
    )
    assert Settings().concurrency == 8
    assert Settings().per_host_delay_seconds == 7.0
    monkeypatch.setenv("NEWSDOCK_CONCURRENCY", "4")
    assert Settings().concurrency == 4


def test_backoff_list_is_parsed_and_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSDOCK_RETRY_BACKOFF_MINUTES", "1, 10, 60")
    assert Settings().retry_backoff() == (1, 10, 60)
    monkeypatch.setenv("NEWSDOCK_RETRY_BACKOFF_MINUTES", "soon")
    with pytest.raises(ValueError):
        Settings()
