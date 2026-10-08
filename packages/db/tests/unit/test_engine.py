"""Engine factories use the psycopg driver, do not connect, and honour pool settings."""

from newsdock_db.config import Settings
from newsdock_db.engine import make_async_engine, make_engine

URL = "postgresql+psycopg://u:p@localhost:5433/db"


def test_sync_engine_uses_psycopg() -> None:
    engine = make_engine(Settings(database_url=URL))
    assert engine.dialect.driver == "psycopg"
    assert engine.url.database == "db"


def test_async_engine_uses_psycopg() -> None:
    engine = make_async_engine(Settings(database_url=URL))
    assert engine.dialect.driver == "psycopg"


def test_tc17_pool_settings_reach_the_engine() -> None:
    settings = Settings(
        database_url=URL,
        database_pool_size=3,
        database_max_overflow=4,
        database_pool_recycle_seconds=600,
        database_pool_pre_ping=False,
    )
    pool = make_engine(settings).pool
    assert pool.size() == 3  # type: ignore[attr-defined]
    assert pool._max_overflow == 4  # type: ignore[attr-defined]
    assert pool._recycle == 600
    assert pool._pre_ping is False
