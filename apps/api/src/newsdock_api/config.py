"""Settings for newsdock-api; the only place env vars are read (DR-9)."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")

    log_level: str = "INFO"
    host: str = "0.0.0.0"  # container-internal; compose binds 127.0.0.1 outside
    port: int = 8000
    # Host headers the MCP transport accepts (DNS-rebinding protection stays on).
    # "api" is the compose-internal name the agent uses (AC-13 network).
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,api:*"
    # Browser origins allowed on /api/* (the web UI); local-only MVP
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h for h in self.mcp_allowed_hosts.split(",") if h]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]

    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
