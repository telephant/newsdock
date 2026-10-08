"""Settings for newsdock_db; the only place DATABASE_URL is read (DR-9).

`DATABASE_URL` is a secret: environment only, never in the config file. The pool
keys live under `common.database` in the file and apply to every process.
"""

from newsdock_config import LayeredSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict


class Settings(LayeredSettings):
    """e.g. DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname."""

    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_")

    database_url: str = Field(
        validation_alias=AliasChoices("DATABASE_URL", "NEWSDOCK_DATABASE_URL")
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle_seconds: int = 1800
    database_pool_pre_ping: bool = True
