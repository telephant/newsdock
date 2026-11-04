"""TC-7/TC-8 (SQL half): `ingest_file` state survives a round trip (needs Docker).

Runs against a throwaway Postgres from the `side_db` fixture, so the dev stack's
database is never touched.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_db.engine import make_engine
from newsdock_ingester.adapters.slots import SqlFileRepo
from newsdock_ingester.domain.ports import FileState

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def repo(side_db: tuple[str, str]) -> SqlFileRepo:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    return SqlFileRepo(make_engine(side_db[0]))


def test_save_get_and_update_a_file_state(repo: SqlFileRepo) -> None:
    assert repo.get("20261102110000", "events") is None
    repo.save(FileState(slot="20261102110000", kind="events", status="pending"))
    stored = repo.get("20261102110000", "events")
    assert stored == FileState(slot="20261102110000", kind="events", status="pending")
    repo.save(
        FileState(
            slot="20261102110000",
            kind="events",
            status="published",
            attempts=2,
            row_count=996,
        )
    )
    stored = repo.get("20261102110000", "events")
    assert stored is not None
    assert (stored.status, stored.attempts, stored.row_count) == ("published", 2, 996)
    assert repo.get("20261102110000", "mentions") is None  # kinds are independent


def test_pending_lists_only_open_files_under_the_attempt_limit(
    repo: SqlFileRepo,
) -> None:
    repo.save(FileState(slot="20261102120000", kind="mentions", status="pending"))
    repo.save(
        FileState(slot="20261102120000", kind="events", status="pending", attempts=3)
    )
    repo.save(
        FileState(slot="20261102121500", kind="events", status="pending", attempts=4)
    )
    repo.save(
        FileState(slot="20261102121500", kind="mentions", status="failed", attempts=4)
    )
    pending = repo.pending(max_attempts=4)
    assert [(s.slot, s.kind) for s in pending] == [
        ("20261102120000", "events"),
        ("20261102120000", "mentions"),
    ]
