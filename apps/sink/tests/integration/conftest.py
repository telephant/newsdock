"""The `side_db` fixture: a throwaway Postgres for Docker tests.

A thin wrapper over `newsdock_db.testing.side_postgres` (own compose project, free
port, container checked to be up and to own the port). It also points DATABASE_URL
at that database for the module, so Alembic and the app code reach it and never the
dev stack's database.
"""

from collections.abc import Iterator

import pytest
from newsdock_db.testing import side_postgres


@pytest.fixture(scope="module")
def side_db(request: pytest.FixtureRequest) -> Iterator[tuple[str, str]]:
    """Yields (SQLAlchemy URL, libpq DSN) of the side Postgres."""
    name = request.module.__name__.rsplit(".", 1)[-1].replace("_", "-")
    mp = pytest.MonkeyPatch()
    with side_postgres(f"newsdock-side-{name}") as (url, dsn):
        mp.setenv("DATABASE_URL", url)
        try:
            yield url, dsn
        finally:
            mp.undo()
