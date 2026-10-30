"""TC-3 (schema), TC-5 (first owner), repo halves of TC-15 and TC-26 (Docker)."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.users_repo import SqlUsersRepo
from newsdock_api.domain.accounts import (
    DuplicateEmail,
    LastOwner,
    Role,
)
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
IDLE = timedelta(hours=12)
NO_SUCH_UUID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    url = side_db[0]
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture()
def repo(engine: Engine) -> SqlUsersRepo:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    return SqlUsersRepo(engine)


def _race(calls: list) -> list:  # type: ignore[type-arg]
    """Run callables at once; return each outcome (value or the raised exception)."""
    barrier = threading.Barrier(len(calls))
    outcomes: list = [None] * len(calls)  # type: ignore[type-arg]

    def run(i: int) -> None:
        barrier.wait()
        try:
            outcomes[i] = calls[i]()
        except Exception as exc:
            outcomes[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return outcomes


# ---- TC-3: schema -------------------------------------------------------------
def test_role_check_unique_email_and_cascade(
    engine: Engine, repo: SqlUsersRepo
) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role) "
                "VALUES ('r@x.io', 'h', 'root')"
            )
        )
    first = repo.create_user("dup@x.io", "h1")
    with pytest.raises(DuplicateEmail):
        repo.create_user("dup@x.io", "h2")
    repo.create_session(first.id, "tok1", NOW, NOW + timedelta(days=7))
    assert repo.delete_user_sessions(NO_SUCH_UUID) == 0
    # deleting a user (a viewer here, so the last-owner rule does not apply) cascades
    other = repo.create_user("other@x.io", "h3")
    repo.create_session(other.id, "tok2", NOW, NOW + timedelta(days=7))
    assert repo.delete_user(other.id)
    assert repo.find_session("tok2") is None
    assert repo.find_session("tok1") is not None


def test_api_role_has_exactly_the_needed_privileges(engine: Engine) -> None:
    with engine.connect() as conn:

        def priv(table: str, what: str) -> bool:
            return bool(
                conn.execute(
                    text("SELECT has_table_privilege('api_rw', :t, :p)"),
                    {"t": table, "p": what},
                ).scalar()
            )

        for table in ("users", "sessions"):
            assert all(priv(table, p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE"))
        assert not priv("users", "TRUNCATE")
        assert not priv("sessions", "TRUNCATE")


# ---- TC-5: first owner ---------------------------------------------------------
def test_first_account_is_owner_then_viewers(repo: SqlUsersRepo) -> None:
    a = repo.create_user("a@x.io", "h")
    b = repo.create_user("b@x.io", "h")
    assert (a.role, b.role) == (Role.OWNER, Role.VIEWER)
    assert repo.find_by_email("a@x.io") == a
    assert repo.find_by_email("nobody@x.io") is None
    assert repo.get_by_id(b.id) == b
    assert repo.get_by_id("not-a-uuid") is None
    assert [u.email for u in repo.list_users()] == ["a@x.io", "b@x.io"]


def test_concurrent_first_signups_yield_exactly_one_owner(
    engine: Engine, repo: SqlUsersRepo
) -> None:
    for round_no in range(20):
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE users CASCADE"))
        outcomes = _race(
            [lambda i=i: repo.create_user(f"u{i}@x.io", "h") for i in range(8)]
        )
        assert all(not isinstance(o, Exception) for o in outcomes), outcomes
        roles = sorted(o.role for o in outcomes)
        assert roles == [Role.OWNER] + [Role.VIEWER] * 7, (round_no, roles)


# ---- TC-26 (repo half): role changes and the last owner -----------------------
def test_promote_and_last_owner_rules(repo: SqlUsersRepo) -> None:
    owner = repo.create_user("o@x.io", "h")
    viewer = repo.create_user("v@x.io", "h")
    assert repo.set_role(viewer.id, Role.ADMIN)
    assert repo.get_by_id(viewer.id).role == Role.ADMIN  # type: ignore[union-attr]
    with pytest.raises(LastOwner):
        repo.set_role(owner.id, Role.VIEWER)
    with pytest.raises(LastOwner):
        repo.delete_user(owner.id)
    assert repo.get_by_id(owner.id).role == Role.OWNER  # type: ignore[union-attr]
    assert not repo.set_role(NO_SUCH_UUID, Role.ADMIN)
    assert not repo.set_role("not-a-uuid", Role.ADMIN)
    assert not repo.delete_user("not-a-uuid")


def test_a_second_owner_makes_the_first_removable(repo: SqlUsersRepo) -> None:
    first = repo.create_user("o1@x.io", "h")
    second = repo.create_user("o2@x.io", "h")
    assert repo.set_role(second.id, Role.OWNER)
    assert repo.set_role(first.id, Role.VIEWER)
    with pytest.raises(LastOwner):
        repo.set_role(second.id, Role.ADMIN)


def test_two_owners_demoting_each_other_never_leave_zero_owners(
    engine: Engine, repo: SqlUsersRepo
) -> None:
    for _ in range(20):
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE users CASCADE"))
        a = repo.create_user("a@x.io", "h")
        b = repo.create_user("b@x.io", "h")
        repo.set_role(b.id, Role.OWNER)
        outcomes = _race(
            [
                lambda: repo.set_role(a.id, Role.VIEWER),
                lambda: repo.set_role(b.id, Role.VIEWER),
            ]
        )
        failures = [o for o in outcomes if isinstance(o, LastOwner)]
        assert len(failures) == 1, outcomes
        owners = [u for u in repo.list_users() if u.role == Role.OWNER]
        assert len(owners) == 1


def test_two_owners_deleting_each_other_never_leave_zero_owners(
    engine: Engine, repo: SqlUsersRepo
) -> None:
    for _ in range(20):
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE users CASCADE"))
        a = repo.create_user("a@x.io", "h")
        b = repo.create_user("b@x.io", "h")
        repo.set_role(b.id, Role.OWNER)
        outcomes = _race(
            [lambda: repo.delete_user(a.id), lambda: repo.delete_user(b.id)]
        )
        assert sum(isinstance(o, LastOwner) for o in outcomes) == 1, outcomes
        assert len(repo.list_users()) == 1


# ---- TC-15 (repo half): sessions ------------------------------------------------
def test_session_roundtrip_touch_and_delete(repo: SqlUsersRepo) -> None:
    user = repo.create_user("s@x.io", "h")
    repo.create_session(user.id, "hash-1", NOW, NOW + timedelta(days=7))
    found = repo.find_session("hash-1")
    assert found is not None
    assert (found.user_id, found.email, found.role) == (user.id, "s@x.io", Role.OWNER)
    assert found.last_seen_at == NOW
    assert found.expires_at == NOW + timedelta(days=7)

    later = NOW + timedelta(minutes=5)
    repo.touch_session("hash-1", later)
    assert repo.find_session("hash-1").last_seen_at == later  # type: ignore[union-attr]

    assert repo.find_session("unknown") is None
    assert repo.delete_session("hash-1")
    assert not repo.delete_session("hash-1")
    assert repo.find_session("hash-1") is None


def test_session_sees_a_role_change_at_once(repo: SqlUsersRepo) -> None:
    repo.create_user("o@x.io", "h")
    viewer = repo.create_user("v@x.io", "h")
    repo.create_session(viewer.id, "hash-v", NOW, NOW + timedelta(days=7))
    assert repo.find_session("hash-v").role == Role.VIEWER  # type: ignore[union-attr]
    repo.set_role(viewer.id, Role.ADMIN)
    assert repo.find_session("hash-v").role == Role.ADMIN  # type: ignore[union-attr]


def test_delete_user_sessions_removes_only_that_users_sessions(
    repo: SqlUsersRepo,
) -> None:
    a = repo.create_user("a@x.io", "h")
    b = repo.create_user("b@x.io", "h")
    for token, user in (("a1", a), ("a2", a), ("b1", b)):
        repo.create_session(user.id, token, NOW, NOW + timedelta(days=7))
    assert repo.delete_user_sessions(a.id) == 2
    assert repo.find_session("a1") is None and repo.find_session("b1") is not None


def test_delete_expired_removes_absolute_and_idle_expired_rows(
    engine: Engine, repo: SqlUsersRepo
) -> None:
    user = repo.create_user("e@x.io", "h")
    repo.create_session(user.id, "fresh", NOW, NOW + timedelta(days=7))
    repo.create_session(
        user.id, "absolute-gone", NOW - timedelta(days=8), NOW - timedelta(days=1)
    )
    repo.create_session(
        user.id, "idle-gone", NOW - timedelta(days=1), NOW + timedelta(days=6)
    )
    repo.touch_session("idle-gone", NOW - IDLE - timedelta(minutes=1))
    assert repo.delete_expired(NOW, IDLE) == 2
    assert repo.find_session("fresh") is not None
    assert repo.find_session("absolute-gone") is None
    assert repo.find_session("idle-gone") is None


def test_set_password_hash_replaces_only_the_hash(repo: SqlUsersRepo) -> None:
    user = repo.create_user("p@x.io", "old-hash")
    assert repo.set_password_hash(user.id, "new-hash")
    after = repo.get_by_id(user.id)
    assert after is not None and after.password_hash == "new-hash"
    assert (after.email, after.role) == (user.email, user.role)
    assert not repo.set_password_hash(NO_SUCH_UUID, "x")
    assert not repo.set_password_hash("not-a-uuid", "x")
