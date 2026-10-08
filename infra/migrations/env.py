"""Alembic environment: URL and metadata come from newsdock_db (DR-9, ADR-0008)."""

from alembic import context
from newsdock_db import models  # noqa: F401  (registers tables on the metadata)
from newsdock_db.config import Settings
from newsdock_db.engine import make_engine
from newsdock_db.metadata import metadata

target_metadata = metadata


def run_migrations_online() -> None:
    engine = make_engine(Settings())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not supported; connect to the database")
run_migrations_online()
