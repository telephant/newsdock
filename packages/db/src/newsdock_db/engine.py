"""Engine factories. Creating an engine does not open a connection.

Pass a `Settings` (pool options from config) or a bare URL (defaults, used by tests).
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from newsdock_db.config import Settings


def _settings(source: Settings | str) -> Settings:
    return source if isinstance(source, Settings) else Settings(database_url=source)


def make_engine(source: Settings | str) -> Engine:
    s = _settings(source)
    return create_engine(
        s.database_url,
        pool_size=s.database_pool_size,
        max_overflow=s.database_max_overflow,
        pool_recycle=s.database_pool_recycle_seconds,
        pool_pre_ping=s.database_pool_pre_ping,
    )


def make_async_engine(source: Settings | str) -> AsyncEngine:
    s = _settings(source)
    return create_async_engine(
        s.database_url,
        pool_size=s.database_pool_size,
        max_overflow=s.database_max_overflow,
        pool_recycle=s.database_pool_recycle_seconds,
        pool_pre_ping=s.database_pool_pre_ping,
    )
