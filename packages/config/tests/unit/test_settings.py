"""TC-1, TC-2, TC-3, TC-5, TC-6, TC-7, TC-26: layered settings behaviour."""

from pathlib import Path

import pytest
from newsdock_config import ConfigError, LayeredSettings, load_settings
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import SettingsConfigDict


class Svc(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "svc"

    log_level: str = "INFO"
    poll_interval_seconds: int = 900
    kafka_topics_clean: str = "gkg.clean"
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
    api_token: str = "default-token"

    @field_validator("poll_interval_seconds")
    @classmethod
    def _floor(cls, v: int) -> int:
        return max(v, 900)


class Other(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "other"

    log_level: str = "INFO"
    kafka_topics_clean: str = "gkg.clean"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "NEWSDOCK_LOG_LEVEL",
        "NEWSDOCK_POLL_INTERVAL_SECONDS",
        "NEWSDOCK_KAFKA_TOPICS_CLEAN",
        "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS",
        "KAFKA_BOOTSTRAP_SERVERS",
    ):
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Path:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))
    return path


def test_defaults_without_file() -> None:
    s = Svc()
    assert s.poll_interval_seconds == 900
    assert s.kafka_topics_clean == "gkg.clean"


def test_tc1_file_value_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "svc:\n  poll_interval_seconds: 1800\n")
    assert Svc().poll_interval_seconds == 1800


def test_tc2_common_inherited_and_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  log_level: DEBUG\n  kafka:\n    topics:\n      clean: x.clean\n"
        "svc:\n  log_level: WARNING\n",
    )
    svc, other = Svc(), Other()
    assert svc.log_level == "WARNING"
    assert other.log_level == "DEBUG"
    assert svc.kafka_topics_clean == "x.clean"  # nested common key flattened
    assert other.kafka_topics_clean == "x.clean"


def test_tc3_env_beats_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, monkeypatch, "svc:\n  poll_interval_seconds: 1800\n")
    monkeypatch.setenv("NEWSDOCK_POLL_INTERVAL_SECONDS", "2400")
    assert Svc().poll_interval_seconds == 2400


def test_tc3_env_beats_file_for_aliased_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  kafka:\n    bootstrap_servers: kafka:9092\n",
    )
    assert Svc().kafka_bootstrap_servers == "kafka:9092"  # file only
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "envk:1")
    assert Svc().kafka_bootstrap_servers == "envk:1"
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS")
    monkeypatch.setenv("NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS", "envp:2")
    assert Svc().kafka_bootstrap_servers == "envp:2"


def test_validators_run_after_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "svc:\n  poll_interval_seconds: 60\n")
    assert Svc().poll_interval_seconds == 900


def test_tc5_missing_explicit_file_names_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", "/no/such/newsdock.yaml")
    with pytest.raises(ConfigError, match="/no/such/newsdock.yaml"):
        Svc()


def test_tc5_unparsable_yaml_names_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(tmp_path, monkeypatch, "svc: [unclosed\n")
    with pytest.raises(ConfigError, match=str(path)):
        Svc()


def test_tc5_unset_variable_is_not_an_error() -> None:
    assert Svc().log_level == "INFO"


def test_tc6_unknown_service_key_names_section_and_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "svc:\n  batchsize: 3\n")
    with pytest.raises(ConfigError, match=r"svc\.batchsize"):
        Svc()


def test_tc6_unknown_common_key_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "common:\n  only_for_others: 1\n")
    assert Svc().log_level == "INFO"


def test_other_sections_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "other:\n  log_level: ERROR\n")
    assert Svc().log_level == "INFO"


@pytest.mark.parametrize(
    "key",
    ["database_url", "password", "db_password", "api_token", "client_secret", "pg_dsn"],
)
@pytest.mark.parametrize("where", ["common", "svc"])
def test_tc7_secret_keys_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, where: str
) -> None:
    write(tmp_path, monkeypatch, f"{where}:\n  {key}: hunter2\n")
    with pytest.raises(ConfigError, match=key):
        Svc()


def test_tc7_secret_key_rejected_even_in_unrelated_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "other:\n  password: x\n")
    with pytest.raises(ConfigError, match="password"):
        Svc()


def test_tc26_redacted_hides_secret_fields() -> None:
    shown = Svc().redacted()
    assert shown["api_token"] == "***"
    assert shown["log_level"] == "INFO"


def test_tc5_load_settings_exits_nonzero_with_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", "/no/such/newsdock.yaml")
    with pytest.raises(SystemExit) as exc:
        load_settings(Svc)
    assert exc.value.code == 2
    assert "/no/such/newsdock.yaml" in capsys.readouterr().err


def test_load_settings_reports_type_errors_with_field_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write(tmp_path, monkeypatch, "svc:\n  poll_interval_seconds: many\n")
    with pytest.raises(SystemExit):
        load_settings(Svc)
    assert "poll_interval_seconds" in capsys.readouterr().err


def test_load_settings_returns_settings_when_valid() -> None:
    assert load_settings(Svc).poll_interval_seconds == 900
