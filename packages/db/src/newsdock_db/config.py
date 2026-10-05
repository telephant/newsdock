"""Settings for newsdock_db; the only place DATABASE_URL is read (DR-9)."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Reads DATABASE_URL, e.g. postgresql+psycopg://user:password@host:5432/dbname."""

    database_url: str
