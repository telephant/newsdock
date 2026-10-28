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
    "cors_allow_methods": "GET,POST,PATCH,DELETE",  # ui-login: writes (ADR-0021)
    "cors_allow_headers": "Content-Type,Last-Event-ID",
    "cors_allow_cookies": True,
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


# TC-11 (config part): auth defaults and the committed file
def test_auth_settings_defaults() -> None:
    s = Settings()
    assert s.auth_required is True
    assert s.rate_limit_per_minute == 600
    assert s.admin_token is None


def test_admin_token_comes_from_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSDOCK_ADMIN_TOKEN", "s3cret")
    token = Settings().admin_token
    assert token is not None and token.get_secret_value() == "s3cret"
    assert "s3cret" not in repr(Settings())


def test_committed_yaml_lists_auth_defaults_and_no_secret() -> None:
    import yaml

    raw = yaml.safe_load((ROOT / "infra/config/newsdock.yaml").read_text())
    assert raw["api"]["auth_required"] is True
    assert raw["api"]["rate_limit_per_minute"] == 600
    assert "admin_token" not in raw["api"]


# TC-34 (AC-13, AC-3): account settings, defaults and the committed file
AUTH_DEFAULTS = {
    "auth_signup_open": True,
    "auth_min_pw_length": 10,
    "auth_session_idle_hours": 12,
    "auth_session_absolute_days": 7,
    "auth_login_max_failures": 5,
    "auth_login_window_minutes": 15,
    "auth_cookie_secure": False,
    "auth_cookie_name": "newsdock_session",
}


def test_account_settings_defaults() -> None:
    s = Settings()
    for name, value in AUTH_DEFAULTS.items():
        assert getattr(s, name) == value, name
    assert s.session_idle == timedelta(hours=12)
    assert s.session_absolute == timedelta(days=7)
    assert s.login_window_seconds == 15 * 60


def test_committed_yaml_rows_equal_the_account_defaults() -> None:
    import yaml

    raw = yaml.safe_load((ROOT / "infra/config/newsdock.yaml").read_text())
    for name, value in AUTH_DEFAULTS.items():
        assert raw["api"][name] == value, name


# TC-22 (AC-15): sign-up limits and the agent quota (signup-rate-limit)
LIMIT_DEFAULTS = {
    "auth_signup_max_per_address": 5,
    "auth_signup_max_total": 50,
    "auth_signup_window_minutes": 60,
    "agents_max_per_user": 10,
}


def test_signup_limit_settings_defaults() -> None:
    s = Settings()
    for name, value in LIMIT_DEFAULTS.items():
        assert getattr(s, name) == value, name
    assert s.signup_window_seconds == 3600


def test_committed_yaml_rows_equal_the_limit_defaults() -> None:
    import yaml

    raw = yaml.safe_load((ROOT / "infra/config/newsdock.yaml").read_text())
    for name, value in LIMIT_DEFAULTS.items():
        assert raw["api"][name] == value, name


def test_signup_limits_can_be_overridden_and_switched_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "api:\n  auth_signup_max_total: 0\n")
    assert Settings().auth_signup_max_total == 0
    monkeypatch.setenv("NEWSDOCK_AGENTS_MAX_PER_USER", "3")
    assert Settings().agents_max_per_user == 3


def test_account_settings_can_be_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "api:\n  auth_signup_open: false\n")
    assert Settings().auth_signup_open is False
    monkeypatch.setenv("NEWSDOCK_AUTH_LOGIN_MAX_FAILURES", "2")
    assert Settings().auth_login_max_failures == 2
