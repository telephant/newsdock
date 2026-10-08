"""Settings for newsdock-agent; the only place env vars are read (DR-9).

AC-13: the agent configuration can name only the MCP and Ollama endpoints —
no database or Kafka settings exist, and unknown keys are rejected
(extra="forbid", TC-35). It loads `common` keys it declares (e.g. log_level) and
its own `agent` section; Kafka and database values in the shared file never reach it.
"""

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import SettingsConfigDict


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_AGENT_", extra="forbid")
    section = "agent"

    log_level: str = "INFO"
    mcp_url: str = Field(
        default="http://127.0.0.1:8000/mcp",
        validation_alias=AliasChoices("MCP_URL", "NEWSDOCK_AGENT_MCP_URL"),
    )
    ollama_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_URL", "NEWSDOCK_AGENT_OLLAMA_URL"),
    )
    model: str = "llama3.2:3b"  # chosen in the T-01 spike (spike.md §2)
    agent_name: str = "demo-financial"
    theme_prefixes: str = "ECON_"  # comma-separated; spike decision 2026-10-05
    cursor_file: str = "/data/cursor.json"
    heartbeat_file: str = "/tmp/healthy"
    heartbeat_max_age_seconds: int = 0  # 0 = derive: 2 x loop interval
    loop_interval_seconds: int = 60
    batch_limit: int = 200
    ollama_timeout_seconds: float = 120.0
    ollama_temperature: float = 0.0
    eval_threshold: float = 0.5  # CLI --threshold still wins (AC-14 of M1)
    export_limit: int = 100
    export_timeout_seconds: float = 30.0

    @model_validator(mode="after")
    def _derive_heartbeat_max_age(self) -> "Settings":
        if self.heartbeat_max_age_seconds <= 0:
            self.heartbeat_max_age_seconds = 2 * self.loop_interval_seconds
        return self

    @property
    def prefixes(self) -> tuple[str, ...]:
        return tuple(p for p in self.theme_prefixes.split(",") if p)
