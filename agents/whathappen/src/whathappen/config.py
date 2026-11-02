"""Settings of the what-happen agent server: the only place environment is read.

Every setting is an environment variable with the prefix `WHATHAPPEN_`; values are also
read from `agents/whathappen/.env` (git-ignored), wherever the process is started from.
The agent reaches the platform only over HTTP (MCP) and the host's Ollama, so there are
no database or Kafka settings at all.
"""

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from whathappen.domain.sections import (
    DEFAULT_SECTIONS,
    SectionLabels,
    parse_section_labels,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # agents/whathappen


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WHATHAPPEN_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # the .env also holds compose-only keys (WHATHAPPEN_DOCKER_*)
    )

    log_level: str = "INFO"

    # The platform: the MCP endpoint and this agent's own key (created by a person in
    # the website at /admin/agents; shown once). The key is a secret: .env only.
    mcp_url: str = "http://127.0.0.1:8000/mcp"
    api_key: SecretStr | None = None
    page_size: int = 200  # articles per MCP page; the server's maximum is 200

    # Ollama on the host
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:4b-instruct"
    ollama_timeout_seconds: float = 120.0
    ollama_temperature: float = 0.0

    # The digest
    interval_seconds: int = 3600
    output_dir: str = "output"
    state_file: str = "output/baseline.json"
    max_themes: int = 8
    stories_per_theme: int = 3
    prompt_titles: int = 3  # = stories shown, so a sentence can be checked
    min_theme_count: int = 5
    skip_theme_prefixes: str = (
        "TAX_,WB_,EPU_,CRISISLEX_,USPEC_,UNGP_,GENERAL_,MEDIA_,SOC_,LEADER,AFFECT"
    )
    max_articles: int = 20000
    baseline_hours: int = 24
    baseline_min_entries: int = 3
    baseline_themes_kept: int = 2000
    summary_max_chars: int = 300

    # The story-first digest (spec digest-top-stories)
    top_stories: int = 5  # groups in the Top stories block
    max_sections: int = 6
    groups_per_section: int = 4
    min_group_sources: int = 2  # a group carried by fewer outlets is not listed
    also_per_group: int = 3  # other headlines shown, and sent to the model, per group
    group_window_hours: int = 48  # a headline joins a group within this of its seed
    match_overlap: float = 0.75
    match_jaccard: float = 0.5
    match_min_shared: int = 3
    tone_divisor: float = 10.0  # score = sources x (1 + tone_neg / divisor)
    section_min_hits: int = 1  # theme hits a label needs to claim a group
    section_labels: str = ""  # JSON label -> theme prefixes; empty = the built-in map

    heartbeat_file: str = "/tmp/healthy"  # noqa: S108 - container-local liveness file

    @field_validator("section_labels")
    @classmethod
    def _section_labels_must_parse(cls, value: str) -> str:
        if value.strip():
            parse_section_labels(value)  # raises a ValueError naming section_labels
        return value

    @property
    def section_label_map(self) -> SectionLabels:
        if self.section_labels.strip():
            return parse_section_labels(self.section_labels)
        return DEFAULT_SECTIONS

    @property
    def skip_prefixes(self) -> tuple[str, ...]:
        return tuple(p for p in self.skip_theme_prefixes.split(",") if p)

    @property
    def output_path(self) -> Path:
        return _resolve(self.output_dir)

    @property
    def state_path(self) -> Path:
        return _resolve(self.state_file)

    @property
    def heartbeat_max_age_seconds(self) -> int:
        """Twice the interval plus the worst case of one cycle's model calls (one per
        listed group)."""
        calls = self.top_stories + self.max_sections * self.groups_per_section
        return int(2 * self.interval_seconds + self.ollama_timeout_seconds * calls)


def _resolve(value: str) -> Path:
    """Relative paths mean 'inside the project', whatever the working directory is."""
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path
