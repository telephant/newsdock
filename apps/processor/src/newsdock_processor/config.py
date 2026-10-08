"""Settings for newsdock-processor; the only place env vars are read (DR-9)."""

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "processor"

    log_level: str = "INFO"
    heartbeat_file: str = "/tmp/healthy"
    heartbeat_max_age_seconds: int = 120
    batch_size: int = 200
    poll_timeout_seconds: float = 1.0
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
    kafka_topics_raw: str = "gkg.raw"
    kafka_topics_clean: str = "gkg.clean"
    kafka_topics_dlq: str = "gkg.dlq"
    kafka_group_id: str = "processor"
    kafka_auto_offset_reset: str = "earliest"
    # Topic job (adapters/topics.py): single broker, ordering over throughput (M1).
    kafka_topic_partitions: int = 1
    kafka_topic_replication_factor: int = 1
