"""Settings for newsdock-sink; the only place env vars are read (DR-9)."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")

    log_level: str = "INFO"
    heartbeat_file: str = "/tmp/healthy"
    batch_size: int = 200
    batch_window_seconds: float = 1.0
    db_backoff_seconds: float = 5.0
    retention_interval_seconds: int = 3600
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
