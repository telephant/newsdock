"""TC-1, TC-2, TC-3, TC-4: sink configuration."""

import json
from pathlib import Path

import pytest
from newsdock_sink.config import Settings

ROOT = Path(__file__).resolve().parents[4]
BEFORE = json.loads(
    (ROOT / "infra/scripts/tests/fixtures/config_defaults_before.json").read_text()
)["sink"]
NEW_DEFAULTS = {
    "retention_days": 7,
    "kafka_topics_clean": "gkg.clean",
    "kafka_topics_dlq": "gkg.dlq",
    "kafka_group_id": "sink",
    "kafka_auto_offset_reset": "earliest",
    "heartbeat_max_age_seconds": 120,
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "NEWSDOCK_LOG_LEVEL",
        "NEWSDOCK_RETENTION_DAYS",
        "NEWSDOCK_STORY_WINDOW_HOURS",
        "KAFKA_BOOTSTRAP_SERVERS",
        "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS",
    ):
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))


def test_tc4_defaults_equal_the_before_snapshot_and_inventory() -> None:
    settings = Settings()
    for name, value in BEFORE.items():
        assert getattr(settings, name) == value, name
    for name, value in NEW_DEFAULTS.items():
        assert getattr(settings, name) == value, name


def test_tc1_tc2_file_and_common_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  kafka:\n    topics:\n      clean: c.test\n      dlq: d.test\n"
        "sink:\n  retention_days: 3\n  story_window_hours: 24\n",
    )
    s = Settings()
    assert (s.kafka_topics_clean, s.kafka_topics_dlq) == ("c.test", "d.test")
    assert (s.retention_days, s.story_window_hours) == (3, 24)


def test_tc3_env_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, monkeypatch, "sink:\n  retention_days: 3\n")
    monkeypatch.setenv("NEWSDOCK_RETENTION_DAYS", "5")
    assert Settings().retention_days == 5
