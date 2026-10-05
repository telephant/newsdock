"""Settings for newsdock-ingester; the only place env vars are read (DR-9)."""

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_POLL_INTERVAL_SECONDS = 900  # GDELT rule: never poll faster than 15 min


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")

    log_level: str = "INFO"
    gdelt_base_url: str = "http://data.gdeltproject.org/gdeltv2"
    poll_interval_seconds: int = MIN_POLL_INTERVAL_SECONDS
    heartbeat_file: str = "/tmp/healthy"
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )

    @field_validator("poll_interval_seconds")
    @classmethod
    def _enforce_floor(cls, v: int) -> int:
        return max(v, MIN_POLL_INTERVAL_SECONDS)
