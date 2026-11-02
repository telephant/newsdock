"""Settings of the independent server (AC-15): env, its own .env, no platform keys."""

from pathlib import Path

import pytest

from whathappen.config import PROJECT_ROOT, Settings


def test_defaults_match_the_documented_values() -> None:
    s = Settings()
    assert s.mcp_url == "http://127.0.0.1:8000/mcp"
    assert s.api_key is None
    assert s.ollama_url == "http://127.0.0.1:11434"
    assert s.model == "qwen3:4b-instruct"
    assert (s.page_size, s.interval_seconds) == (200, 3600)
    assert (s.max_themes, s.stories_per_theme, s.prompt_titles) == (8, 3, 3)
    assert (s.min_theme_count, s.max_articles) == (5, 20000)
    assert (s.baseline_hours, s.baseline_min_entries) == (24, 3)
    assert (s.baseline_themes_kept, s.summary_max_chars) == (2000, 300)
    assert s.skip_prefixes[:2] == ("TAX_", "WB_")


def test_it_has_no_database_or_kafka_settings_at_all() -> None:
    names = " ".join(Settings.model_fields)
    for word in ("database", "postgres", "kafka", "dsn"):
        assert word not in names


def test_environment_variables_use_the_whathappen_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHATHAPPEN_MODEL", "llama3.2:3b")
    monkeypatch.setenv("WHATHAPPEN_MAX_THEMES", "5")
    monkeypatch.setenv("NEWSDOCK_AGENT_MODEL", "ignored")  # the platform's prefix
    s = Settings()
    assert (s.model, s.max_themes) == ("llama3.2:3b", 5)


def test_the_projects_own_dotenv_is_read_and_unrelated_keys_are_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "WHATHAPPEN_API_KEY=ndk_abc_secret\n"
        "WHATHAPPEN_MCP_URL=http://example.test/mcp\n"
        "WHATHAPPEN_DOCKER_MCP_URL=http://host.docker.internal:8000/mcp\n"
        "SOMETHING_ELSE=1\n"
    )
    monkeypatch.setitem(Settings.model_config, "env_file", env)
    s = Settings()
    assert s.mcp_url == "http://example.test/mcp"
    assert s.api_key is not None and s.api_key.get_secret_value() == "ndk_abc_secret"


def test_the_environment_wins_over_the_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = tmp_path / ".env"
    env.write_text("WHATHAPPEN_MODEL=from-file\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env)
    monkeypatch.setenv("WHATHAPPEN_MODEL", "from-env")
    assert Settings().model == "from-env"


def test_the_api_key_is_never_shown_in_a_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHATHAPPEN_API_KEY", "ndk_abc_secret")
    assert "ndk_abc_secret" not in repr(Settings())


def test_the_dotenv_lives_in_the_project_folder() -> None:
    assert PROJECT_ROOT.name == "whathappen" and PROJECT_ROOT.parent.name == "agents"
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_relative_paths_mean_inside_the_project_and_absolute_ones_stay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    s = Settings()
    assert s.output_path == PROJECT_ROOT / "output"
    assert s.state_path == PROJECT_ROOT / "output" / "baseline.json"
    monkeypatch.setenv("WHATHAPPEN_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("WHATHAPPEN_STATE_FILE", "/state/baseline.json")
    s = Settings()
    assert s.output_path == tmp_path / "out"
    assert s.state_path == Path("/state/baseline.json")


def test_heartbeat_allows_two_intervals_plus_one_cycle_of_model_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 5 + 6 * 4  # top stories + sections x groups per section
    assert Settings().heartbeat_max_age_seconds == 2 * 3600 + 120 * calls
    monkeypatch.setenv("WHATHAPPEN_INTERVAL_SECONDS", "600")
    assert Settings().heartbeat_max_age_seconds == 2 * 600 + 120 * calls
    monkeypatch.setenv("WHATHAPPEN_TOP_STORIES", "3")
    monkeypatch.setenv("WHATHAPPEN_MAX_SECTIONS", "2")
    monkeypatch.setenv("WHATHAPPEN_GROUPS_PER_SECTION", "2")
    assert Settings().heartbeat_max_age_seconds == 2 * 600 + 120 * (3 + 2 * 2)


def test_empty_skip_list_means_no_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHATHAPPEN_SKIP_THEME_PREFIXES", "")
    assert Settings().skip_prefixes == ()


# ---- the story-first digest settings (spec digest-top-stories) -----------------------
def test_story_digest_defaults_match_the_design() -> None:
    s = Settings()
    assert (s.top_stories, s.max_sections, s.groups_per_section) == (5, 6, 4)
    assert (s.min_group_sources, s.also_per_group) == (2, 3)
    assert (s.group_window_hours, s.match_min_shared) == (48, 3)
    assert (s.match_overlap, s.match_jaccard) == (0.75, 0.5)
    assert (s.tone_divisor, s.section_min_hits) == (10.0, 1)


def test_the_default_section_map_is_used_when_nothing_is_set() -> None:
    from whathappen.domain.sections import DEFAULT_SECTIONS

    assert Settings().section_label_map == DEFAULT_SECTIONS


def test_section_labels_can_be_overridden_with_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "WHATHAPPEN_SECTION_LABELS", '{"Sport": ["SPORT"], "Tech": ["SCI"]}'
    )
    assert Settings().section_label_map == (("Sport", ("SPORT",)), ("Tech", ("SCI",)))


def test_invalid_section_labels_fail_at_start_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHATHAPPEN_SECTION_LABELS", "not json")
    with pytest.raises(ValueError, match="section_labels"):
        Settings()
