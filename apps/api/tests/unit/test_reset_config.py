"""TC-21 (AC-13): the password reset settings, the secrets and the feature switch."""

from pathlib import Path

import pytest
import yaml
from newsdock_api.config import Settings
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]
SECRET = "test-reset-secret-0123456789abcdef0123"  # 37 characters
ENV_NAMES = (
    "NEWSDOCK_CONFIG_FILE",
    "NEWSDOCK_SMTP_HOST",
    "NEWSDOCK_SMTP_PORT",
    "NEWSDOCK_SMTP_PASSWORD",
    "NEWSDOCK_RESET_CODE_SECRET",
    "NEWSDOCK_MAIL_FROM",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))


def on(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
        smtp_host="smtp.example.test", mail_from="noreply@example.test",
        reset_code_secret=SECRET,
    )  # fmt: skip
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_defaults_and_the_feature_is_off_out_of_the_box() -> None:
    s = Settings()
    assert (s.smtp_host, s.smtp_port, s.smtp_security) == ("", 587, "starttls")
    assert (s.smtp_user, s.mail_from, s.smtp_timeout_seconds) == ("", "", 10)
    assert s.smtp_password is None and s.reset_code_secret is None
    assert s.auth_reset_code_minutes == 15
    assert s.auth_reset_max_attempts == 5
    assert s.auth_reset_max_per_email == 3
    assert s.auth_reset_max_per_address == 20
    assert s.auth_reset_max_tries_per_address == 20
    assert s.auth_reset_window_minutes == 60
    assert s.password_reset_enabled is False
    assert s.reset_window_seconds == 3600


@pytest.mark.parametrize(
    "overrides,enabled",
    [
        ({}, True),
        ({"smtp_host": ""}, False),
        ({"mail_from": ""}, False),
        ({"smtp_host": "   "}, False),
        ({"reset_code_secret": None}, False),
        ({"smtp_user": "", "smtp_password": None}, True),  # a relay without login
    ],
)
def test_the_feature_needs_host_sender_and_secret(
    overrides: dict[str, object], enabled: bool
) -> None:
    assert on(**overrides).password_reset_enabled is enabled


@pytest.mark.parametrize("empty", ["", "   "])
def test_an_empty_secret_means_not_set(
    empty: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # compose passes `${NEWSDOCK_RESET_CODE_SECRET:-}`, i.e. an empty string when unset
    monkeypatch.setenv("NEWSDOCK_RESET_CODE_SECRET", empty)
    monkeypatch.setenv("NEWSDOCK_SMTP_PASSWORD", empty)
    s = Settings()
    assert s.reset_code_secret is None and s.smtp_password is None
    assert s.password_reset_enabled is False


def test_both_secrets_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEWSDOCK_RESET_CODE_SECRET", SECRET)
    monkeypatch.setenv("NEWSDOCK_SMTP_PASSWORD", "smtp-password-for-tests")
    s = Settings()
    assert s.reset_code_secret is not None
    assert s.reset_code_secret.get_secret_value() == SECRET
    assert s.smtp_password is not None
    assert s.smtp_password.get_secret_value() == "smtp-password-for-tests"


def test_secrets_never_appear_in_repr_or_the_redacted_log_view() -> None:
    s = on(smtp_password="smtp-password-for-tests")
    assert SECRET not in repr(s) and "smtp-password-for-tests" not in repr(s)
    shown = repr(s.redacted())
    assert SECRET not in shown and "smtp-password-for-tests" not in shown


def test_a_short_secret_stops_startup_naming_the_setting() -> None:
    with pytest.raises(ValidationError, match="reset_code_secret"):
        on(reset_code_secret="x" * 31)
    on(reset_code_secret="x" * 32)  # exactly 32 is fine


def test_an_unknown_security_value_stops_startup() -> None:
    with pytest.raises(ValidationError, match="smtp_security"):
        on(smtp_security="tls")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_plain_smtp_is_allowed_for_loopback_hosts(host: str) -> None:
    assert on(smtp_security="none", smtp_host=host).password_reset_enabled


@pytest.mark.parametrize(
    "host", ["smtp.example.test", "10.0.0.5", "localhost.evil.test"]
)
def test_plain_smtp_to_a_remote_host_stops_startup(host: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        on(smtp_security="none", smtp_host=host)


def test_credentials_with_plain_smtp_stop_startup() -> None:
    with pytest.raises(ValidationError, match="plain"):
        on(smtp_security="none", smtp_host="localhost", smtp_user="u")
    with pytest.raises(ValidationError, match="plain"):
        on(smtp_security="none", smtp_host="localhost", smtp_password="p")


def test_env_beats_file_beats_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path, monkeypatch, "api:\n  smtp_port: 2525\n  smtp_host: mail.file.test\n"
    )
    assert Settings().smtp_port == 2525 and Settings().smtp_host == "mail.file.test"
    monkeypatch.setenv("NEWSDOCK_SMTP_PORT", "465")
    assert Settings().smtp_port == 465


@pytest.mark.parametrize("key", ["smtp_password", "reset_code_secret"])
def test_a_secret_key_in_the_yaml_is_rejected(
    key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, f"api:\n  {key}: do-not-put-secrets-here\n")
    with pytest.raises(Exception, match=key):
        Settings()


def test_the_committed_yaml_lists_the_defaults_and_no_secret() -> None:
    raw = yaml.safe_load((ROOT / "infra/config/newsdock.yaml").read_text())["api"]
    defaults = Settings()
    for key in (
        "smtp_host", "smtp_port", "smtp_security", "smtp_user", "mail_from",
        "smtp_timeout_seconds", "auth_reset_code_minutes", "auth_reset_max_attempts",
        "auth_reset_max_per_email", "auth_reset_max_per_address",
        "auth_reset_max_tries_per_address", "auth_reset_window_minutes",
    ):  # fmt: skip
        assert raw[key] == getattr(defaults, key), key
    assert "smtp_password" not in raw and "reset_code_secret" not in raw
