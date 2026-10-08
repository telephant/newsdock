"""TC-1, TC-2, TC-3, TC-4, TC-5, TC-9 (ingester), TC-12: ingester configuration."""

import json
from pathlib import Path

import httpx
import pytest
from newsdock_ingester import __main__ as entry
from newsdock_ingester.adapters import kafka as kafka_adapter
from newsdock_ingester.adapters.gdelt import HttpGdeltSource
from newsdock_ingester.config import Settings

ROOT = Path(__file__).resolve().parents[4]
BEFORE = json.loads(
    (ROOT / "infra/scripts/tests/fixtures/config_defaults_before.json").read_text()
)["ingester"]
NEW_DEFAULTS = {
    "gdelt_index_path": "/lastupdate.txt",
    "http_timeout_seconds": 60.0,
    "max_attempts": 4,
    "kafka_topics_raw": "gkg.raw",
    "heartbeat_max_age_seconds": 1200,
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "NEWSDOCK_LOG_LEVEL",
        "NEWSDOCK_POLL_INTERVAL_SECONDS",
        "NEWSDOCK_MAX_ATTEMPTS",
        "NEWSDOCK_KAFKA_TOPICS_RAW",
        "NEWSDOCK_HEARTBEAT_MAX_AGE_SECONDS",
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


def test_tc1_file_value_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "ingester:\n  poll_interval_seconds: 1800\n")
    assert Settings().poll_interval_seconds == 1800


def test_tc2_common_values_reach_ingester(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  log_level: DEBUG\n  kafka:\n    topics:\n      raw: raw.test\n",
    )
    settings = Settings()
    assert settings.log_level == "DEBUG"
    assert settings.kafka_topics_raw == "raw.test"


def test_tc3_env_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  kafka:\n    bootstrap_servers: kafka:9092\n"
        "ingester:\n  poll_interval_seconds: 1800\n",
    )
    monkeypatch.setenv("NEWSDOCK_POLL_INTERVAL_SECONDS", "2400")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "envk:1")
    settings = Settings()
    assert settings.poll_interval_seconds == 2400
    assert settings.kafka_bootstrap_servers == "envk:1"


def test_tc12_poll_floor_survives_a_low_file_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "ingester:\n  poll_interval_seconds: 60\n")
    assert Settings().poll_interval_seconds == 900


def test_heartbeat_max_age_follows_the_poll_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "ingester:\n  poll_interval_seconds: 1800\n")
    assert Settings().heartbeat_max_age_seconds == 2400


def test_tc5_missing_config_file_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", "/no/such/newsdock.yaml")
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code != 0
    assert "/no/such/newsdock.yaml" in capsys.readouterr().err


def test_tc12_timeout_and_index_path_reach_the_http_source() -> None:
    source = HttpGdeltSource(
        "http://gdelt.test/v2", timeout_seconds=7.0, index_path="/idx.txt"
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")

    assert source._client.timeout.read == 7.0
    source._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert source.fetch_index() == "ok"
    assert seen == ["http://gdelt.test/v2/idx.txt"]


def test_tc9_publisher_uses_the_configured_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    produced: list[str] = []

    class FakeProducer:
        def __init__(self, conf: dict[str, str]) -> None:
            pass

        def produce(self, topic: str, key: bytes, value: bytes) -> None:
            produced.append(topic)

        def poll(self, timeout: float) -> None:
            pass

        def flush(self) -> None:
            pass

    monkeypatch.setattr(kafka_adapter, "Producer", FakeProducer)
    from newsdock_core.contracts import RawMessage

    publisher = kafka_adapter.KafkaRawPublisher("kafka:9092", topic="raw.test")
    publisher.publish("k", RawMessage(slot="20261004081500", row_no=0, line="x"))
    assert produced == ["raw.test"]
