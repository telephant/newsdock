"""Engine factories use the psycopg driver and do not connect on creation."""

from newsdock_db.engine import make_async_engine, make_engine

URL = "postgresql+psycopg://u:p@localhost:5433/db"


def test_sync_engine_uses_psycopg() -> None:
    engine = make_engine(URL)
    assert engine.dialect.driver == "psycopg"
    assert engine.url.database == "db"


def test_async_engine_uses_psycopg() -> None:
    engine = make_async_engine(URL)
    assert engine.dialect.driver == "psycopg"
