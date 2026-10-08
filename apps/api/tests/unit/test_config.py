"""TC-1, TC-2, TC-3, TC-4, TC-16 (settings → limits): API configuration."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from newsdock_api.config import Settings

ROOT = Path(__file__).resolve().parents[4]
BEFORE = json.loads(
    (ROOT / "infra/scripts/tests/fixtures/config_defaults_before.json").read_text()
)["api"]
NEW_DEFAULTS = {
    "cors_allow_methods": "GET",
    "cors_allow_headers": "*",
    "first_run_window_minutes": 60,
    "max_payload_bytes": 65536,
    "search_page_default": 20,
    "search_page_max": 100,
    "list_new_page_default": 50,
    "list_new_page_max": 200,
    "kafka_probe_timeout_seconds": 1.0,
    "uvicorn_workers": 1,
    "uvicorn_log_level": "info",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "NEWSDOCK_LOG_LEVEL",
        "NEWSDOCK_PORT",
        "NEWSDOCK_SEARCH_PAGE_MAX",
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
        "common:\n  log_level: DEBUG\n"
        "api:\n  port: 9000\n  search_page_max: 50\n  first_run_window_minutes: 5\n",
    )
    s = Settings()
    assert (s.log_level, s.port, s.search_page_max) == ("DEBUG", 9000, 50)
    assert s.limits().first_run_window == timedelta(minutes=5)


def test_tc3_env_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, monkeypatch, "api:\n  search_page_max: 50\n")
    monkeypatch.setenv("NEWSDOCK_SEARCH_PAGE_MAX", "60")
    assert Settings().limits().search_max == 60


def test_limits_mirror_the_page_and_payload_settings() -> None:
    limits = Settings().limits()
    assert (limits.search_default, limits.search_max) == (20, 100)
    assert (limits.list_new_default, limits.list_new_max) == (50, 200)
    assert limits.max_payload_bytes == 65536
    assert limits.first_run_window == timedelta(hours=1)


def test_cors_method_and_header_lists() -> None:
    s = Settings(cors_allow_methods="GET,POST", cors_allow_headers="x-a,x-b")
    assert s.cors_methods_list == ["GET", "POST"]
    assert s.cors_headers_list == ["x-a", "x-b"]
