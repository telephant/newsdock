"""TC-1, TC-2, TC-3, TC-4: processor configuration."""

import json
from pathlib import Path

import pytest
from newsdock_processor.config import Settings

ROOT = Path(__file__).resolve().parents[4]
BEFORE = json.loads(
    (ROOT / "infra/scripts/tests/fixtures/config_defaults_before.json").read_text()
)["processor"]
NEW_DEFAULTS = {
    "kafka_topics_raw": "gkg.raw",
    "kafka_topics_clean": "gkg.clean",
    "kafka_topics_dlq": "gkg.dlq",
    "kafka_group_id": "processor",
    "kafka_auto_offset_reset": "earliest",
    "kafka_topic_partitions": 1,
    "kafka_topic_replication_factor": 1,
    "heartbeat_max_age_seconds": 120,
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "NEWSDOCK_LOG_LEVEL",
        "NEWSDOCK_BATCH_SIZE",
        "NEWSDOCK_KAFKA_TOPICS_CLEAN",
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
        "common:\n  log_level: DEBUG\n  kafka:\n    topics:\n      clean: c.test\n"
        "processor:\n  batch_size: 50\n  kafka:\n    group_id: proc-2\n",
    )
    s = Settings()
    assert (s.log_level, s.kafka_topics_clean) == ("DEBUG", "c.test")
    assert (s.batch_size, s.kafka_group_id) == (50, "proc-2")


def test_tc3_env_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, monkeypatch, "processor:\n  batch_size: 50\n")
    monkeypatch.setenv("NEWSDOCK_BATCH_SIZE", "75")
    assert Settings().batch_size == 75
