"""Settings for newsdock-api; the only place env vars are read (DR-9)."""

from datetime import timedelta

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict

from newsdock_api.domain.service import ServiceLimits


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "api"

    log_level: str = "INFO"
    host: str = "0.0.0.0"  # container-internal; compose binds 127.0.0.1 outside
    port: int = 8000
    # Host headers the MCP transport accepts (DNS-rebinding protection stays on).
    # "api" is the compose-internal name the agent uses (AC-13 network).
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,api:*"
    # Browser origins allowed on /api/* (the web UI); local-only MVP
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    cors_allow_methods: str = "GET"
    cors_allow_headers: str = "*"
    # Service limits (spec AC-11): first-run window, payload cap, page sizes
    first_run_window_minutes: int = 60
    max_payload_bytes: int = 64 * 1024
    search_page_default: int = 20
    search_page_max: int = 100
    list_new_page_default: int = 50
    list_new_page_max: int = 200
    kafka_probe_timeout_seconds: float = 1.0
    uvicorn_workers: int = 1
    uvicorn_log_level: str = "info"

    def limits(self) -> ServiceLimits:
        return ServiceLimits(
            search_default=self.search_page_default,
            search_max=self.search_page_max,
            list_new_default=self.list_new_page_default,
            list_new_max=self.list_new_page_max,
            max_payload_bytes=self.max_payload_bytes,
            first_run_window=timedelta(minutes=self.first_run_window_minutes),
        )

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h for h in self.mcp_allowed_hosts.split(",") if h]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]

    @property
    def cors_methods_list(self) -> list[str]:
        return [m for m in self.cors_allow_methods.split(",") if m]

    @property
    def cors_headers_list(self) -> list[str]:
        return [h for h in self.cors_allow_headers.split(",") if h]

    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
