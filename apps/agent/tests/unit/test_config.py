"""TC-35 (M1), TC-1/3/4, TC-18, TC-19: agent configuration and isolation."""

import json
from pathlib import Path

import pytest
from newsdock_agent.config import Settings
from newsdock_config import ConfigError
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]
BEFORE = json.loads(
    (ROOT / "infra/scripts/tests/fixtures/config_defaults_before.json").read_text()
)["agent"]
NEW_DEFAULTS = {
    "batch_limit": 200,
    "ollama_timeout_seconds": 120.0,
    "ollama_temperature": 0.0,
    "eval_threshold": 0.5,
    "export_limit": 100,
    "export_timeout_seconds": 30.0,
    "heartbeat_max_age_seconds": 120,
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "NEWSDOCK_AGENT_LOG_LEVEL",
        "NEWSDOCK_AGENT_MODEL",
        "NEWSDOCK_AGENT_LOOP_INTERVAL_SECONDS",
        "NEWSDOCK_AGENT_HEARTBEAT_MAX_AGE_SECONDS",
        "MCP_URL",
        "NEWSDOCK_AGENT_MCP_URL",
        "OLLAMA_URL",
        "NEWSDOCK_AGENT_OLLAMA_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))


# ---- M1 TC-35 stays true -----------------------------------------------------


def test_config_exposes_no_db_or_kafka_fields() -> None:
    field_names = set(Settings.model_fields)
    assert not {f for f in field_names if "database" in f or "kafka" in f or "dsn" in f}
    assert {"mcp_url", "ollama_url"} <= field_names


def test_unknown_settings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://sneaky")  # type: ignore[call-arg]


def test_unknown_agent_env_vars_never_create_a_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEWSDOCK_AGENT_DATABASE_URL", "postgresql://sneaky")
    # env source ignores unknown prefixed vars; the model still has no such field
    assert "database_url" not in Settings().model_dump()


# ---- externalize-config ---------------------------------------------------------


def test_tc4_defaults_equal_the_before_snapshot_and_inventory() -> None:
    settings = Settings()
    for name, value in BEFORE.items():
        assert getattr(settings, name) == value, name
    for name, value in NEW_DEFAULTS.items():
        assert getattr(settings, name) == value, name


def test_tc1_tc3_file_value_and_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  log_level: DEBUG\n"
        "agent:\n  model: llama3.2:1b\n  mcp_url: http://file:8000/mcp\n",
    )
    s = Settings()
    assert (s.log_level, s.model, s.mcp_url) == (
        "DEBUG",
        "llama3.2:1b",
        "http://file:8000/mcp",
    )
    monkeypatch.setenv("MCP_URL", "http://env:8000/mcp")
    monkeypatch.setenv("NEWSDOCK_AGENT_MODEL", "other")
    s = Settings()
    assert (s.mcp_url, s.model) == ("http://env:8000/mcp", "other")


def test_heartbeat_max_age_is_twice_the_loop_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "agent:\n  loop_interval_seconds: 300\n")
    assert Settings().heartbeat_max_age_seconds == 600


def test_tc18_common_kafka_and_other_sections_do_not_reach_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  log_level: INFO\n  kafka:\n    bootstrap_servers: kafka:9092\n"
        "    topics: {clean: gkg.clean}\n"
        "sink:\n  retention_days: 3\n"
        "agent:\n  model: m\n",
    )
    s = Settings()
    assert s.model == "m"
    assert not {
        f for f in Settings.model_fields if f.startswith(("kafka_", "database_"))
    }
    assert not hasattr(s, "kafka_bootstrap_servers")


@pytest.mark.parametrize("key", ["kafka_bootstrap_servers", "database_pool_size"])
def test_tc19_kafka_or_database_key_in_agent_section_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    write(tmp_path, monkeypatch, f"agent:\n  {key}: x\n")
    with pytest.raises(ConfigError, match=key):
        Settings()
