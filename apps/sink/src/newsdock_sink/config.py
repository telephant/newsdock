"""Settings for newsdock-sink; the only place env vars are read (DR-9)."""

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "sink"

    log_level: str = "INFO"
    heartbeat_file: str = "/tmp/healthy"
    heartbeat_max_age_seconds: int = 120
    batch_size: int = 200
    batch_window_seconds: float = 1.0
    db_backoff_seconds: float = 5.0
    retention_days: int = 7
    retention_interval_seconds: int = 3600
    story_window_hours: int = 48  # D-5 / ADR-0012; env NEWSDOCK_STORY_WINDOW_HOURS
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
    kafka_topics_clean: str = "gkg.clean"
    kafka_topics_dlq: str = "gkg.dlq"
    kafka_group_id: str = "sink"
    kafka_auto_offset_reset: str = "earliest"
