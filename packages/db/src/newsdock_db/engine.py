"""Engine factories. Creating an engine does not open a connection."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def make_async_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)
