"""Settings for newsdock-embedder; the only place env vars are read (DR-9)."""

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict


class Settings(LayeredSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")
    section = "embedder"

    log_level: str = "INFO"
    heartbeat_file: str = "/tmp/healthy"
    # longer than one worst-case loop: Ollama timeout plus the largest backoff
    heartbeat_max_age_seconds: int = 360
    batch_size: int = 32
    poll_interval_seconds: float = 10.0  # pause when nothing is left to embed
    ollama_timeout_seconds: float = 60.0
    backoff_seconds: float = 5.0
    backoff_max_seconds: float = 60.0
    skip_after_failures: int = 3  # a title whose vector keeps being rejected
    skip_table_max_entries: int = 1000

    # shared with the API through `common:` (model and dimension must agree)
    embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = 768
    embedding_document_prefix: str = "search_document: "
    embedding_ollama_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_URL", "NEWSDOCK_EMBEDDING_OLLAMA_URL"),
    )
