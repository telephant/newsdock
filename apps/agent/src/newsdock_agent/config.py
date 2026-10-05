"""Settings for newsdock-agent; the only place env vars are read (DR-9).

AC-13: the agent configuration can name only the MCP and Ollama endpoints —
no database or Kafka settings exist, and unknown NEWSDOCK_AGENT_* vars are
rejected (extra="forbid", TC-35).
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_AGENT_", extra="forbid")

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
    loop_interval_seconds: int = 60

    @property
    def prefixes(self) -> tuple[str, ...]:
        return tuple(p for p in self.theme_prefixes.split(",") if p)
