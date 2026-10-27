"""Settings for newsdock-api; the only place env vars are read (DR-9)."""

from datetime import timedelta

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field, SecretStr
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
    # ui-login (ADR-0021): the browser sends the session cookie, so credentials are
    # allowed and the lists are explicit (a wildcard is not honoured with cookies)
    cors_allow_cookies: bool = True
    cors_allow_methods: str = "GET,POST,PATCH,DELETE"
    cors_allow_headers: str = "Content-Type,Last-Event-ID"
    # Service limits (spec AC-11): first-run window, payload cap, page sizes
    first_run_window_minutes: int = 60
    max_payload_bytes: int = 64 * 1024
    search_page_default: int = 20
    search_page_max: int = 100
    list_new_page_default: int = 50
    list_new_page_max: int = 200
    kafka_probe_timeout_seconds: float = 1.0
    # Agent platform (ADR-0016): keys required on /mcp; per-agent requests/minute
    # (0 = no limit); the admin token is a secret and is read from the environment
    # only (NEWSDOCK_ADMIN_TOKEN). Unset = the token opens nothing (admin/owner
    # sessions still manage agents, ui-login); the reset-password route answers 404.
    auth_required: bool = True
    rate_limit_per_minute: int = 600
    admin_token: SecretStr | None = None
    # Human accounts (M2 ui-login, ADR-0020): sessions, sign-up, login throttle
    auth_signup_open: bool = True
    auth_min_pw_length: int = 10
    auth_session_idle_hours: int = 12
    auth_session_absolute_days: int = 7
    auth_login_max_failures: int = 5  # per account inside the window; 0 = off
    auth_login_window_minutes: int = 15
    auth_cookie_secure: bool = False  # plain-HTTP compose; true behind TLS
    auth_cookie_name: str = "newsdock_session"
    # Push delivery (M2 part 2): subscriptions and SSE streams
    subscriptions_max_per_agent: int = 20
    subscription_text_max_length: int = 200
    sse_max_streams_per_agent: int = 5
    sse_keepalive_seconds: int = 15
    sse_fallback_poll_seconds: int = 30
    live_max_streams_per_user: int = 3  # concurrent live-feed streams per user (429)
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
    def session_idle(self) -> timedelta:
        return timedelta(hours=self.auth_session_idle_hours)

    @property
    def session_absolute(self) -> timedelta:
        return timedelta(days=self.auth_session_absolute_days)

    @property
    def login_window_seconds(self) -> int:
        return self.auth_login_window_minutes * 60

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
