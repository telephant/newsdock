"""Settings for newsdock-processor; the only place env vars are read (DR-9)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")

    log_level: str = "INFO"
