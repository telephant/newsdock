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


# M2 agent-platform: the key is an env-only secret; no local cursor file
def test_api_key_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSDOCK_AGENT_API_KEY", raising=False)
    assert Settings().api_key is None
    monkeypatch.setenv("NEWSDOCK_AGENT_API_KEY", "ndk_abc_def")
    key = Settings().api_key
    assert key is not None and key.get_secret_value() == "ndk_abc_def"
    assert "ndk_abc_def" not in repr(Settings())


def test_cursor_file_setting_is_gone() -> None:
    assert not hasattr(Settings(), "cursor_file")


# M2g what-happen (TC-21): digest settings, defaults from design-detail §1
DIGEST_DEFAULTS = {
    "digest_interval_seconds": 3600,
    "digest_dir": "infra/digests",
    "digest_state_file": "infra/digests/digest-baseline.json",
    "digest_model": "qwen3:4b-instruct",
    "digest_max_themes": 8,
    "digest_stories_per_theme": 3,
    "digest_prompt_titles": 3,
    "digest_min_theme_count": 5,
    "digest_skip_theme_prefixes": (
        "TAX_,WB_,EPU_,CRISISLEX_,USPEC_,UNGP_,GENERAL_,MEDIA_,SOC_,LEADER,AFFECT"
    ),
    "digest_max_articles": 20000,
    "digest_baseline_hours": 24,
    "digest_baseline_min_entries": 3,
    "digest_baseline_themes_kept": 2000,
    "digest_summary_max_chars": 300,
}


def test_digest_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    for name, value in DIGEST_DEFAULTS.items():
        assert getattr(s, name) == value, name


def test_digest_file_rows_equal_the_code_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(ROOT / "infra/config/newsdock.yaml"))
    s = Settings()
    for name, value in DIGEST_DEFAULTS.items():
        assert getattr(s, name) == value, name


def test_digest_file_value_and_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "agent:\n  digest_max_themes: 5\n  digest_dir: /x\n")
    assert (Settings().digest_max_themes, Settings().digest_dir) == (5, "/x")
    monkeypatch.setenv("NEWSDOCK_AGENT_DIGEST_MAX_THEMES", "3")
    assert Settings().digest_max_themes == 3


def test_digest_skip_prefixes_split_and_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert Settings().digest_skip_prefixes[:2] == ("TAX_", "WB_")
    write(tmp_path, monkeypatch, 'agent:\n  digest_skip_theme_prefixes: ""\n')
    assert Settings().digest_skip_prefixes == ()


def test_digest_heartbeat_age_fits_an_hourly_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = Settings()
    # twice the interval plus the worst-case model time of one cycle
    assert s.digest_heartbeat_max_age_seconds == 2 * 3600 + 120 * 8
    # the scoring loop's own age is untouched
    assert s.heartbeat_max_age_seconds == 120
    write(tmp_path, monkeypatch, "agent:\n  digest_interval_seconds: 600\n")
    assert Settings().digest_heartbeat_max_age_seconds == 2 * 600 + 120 * 8


def test_digest_settings_still_reject_database_and_kafka(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "agent:\n  digest_database_url: x\n")
    with pytest.raises(ConfigError, match="digest_database_url"):
        Settings()
