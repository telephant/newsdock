"""Settings for newsdock-ingester; the only place env vars are read (DR-9)."""

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

MIN_POLL_INTERVAL_SECONDS = 900  # GDELT rule: never poll faster than 15 min


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "ingester"

    log_level: str = "INFO"
    gdelt_base_url: str = "http://data.gdeltproject.org/gdeltv2"
    gdelt_index_path: str = "/lastupdate.txt"
    http_timeout_seconds: float = 60.0
    max_attempts: int = 4
    poll_interval_seconds: int = MIN_POLL_INTERVAL_SECONDS
    heartbeat_file: str = "/tmp/healthy"
    heartbeat_max_age_seconds: int = 0  # 0 = derive: 4/3 x poll interval (R-4)
    kafka_bootstrap_servers: str = Field(
        default="127.0.0.1:29092",
        validation_alias=AliasChoices(
            "KAFKA_BOOTSTRAP_SERVERS", "NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS"
        ),
    )
    kafka_topics_raw: str = "gkg.raw"

    @field_validator("poll_interval_seconds")
    @classmethod
    def _enforce_floor(cls, v: int) -> int:
        return max(v, MIN_POLL_INTERVAL_SECONDS)

    @model_validator(mode="after")
    def _derive_heartbeat_max_age(self) -> "Settings":
        if self.heartbeat_max_age_seconds <= 0:
            self.heartbeat_max_age_seconds = -(-self.poll_interval_seconds * 4 // 3)
        return self
