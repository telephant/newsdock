"""TC-23 (AC-5, AC-6; also AC-8, AC-9 at store level): the reset store (Docker)."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.reset_repo import SqlResetRepo
from newsdock_api.adapters.users_repo import SqlUsersRepo
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=15)
OLD_HASH = "old-password-hash"
NEW_HASH = "new-password-hash"


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


@pytest.fixture()
def users(engine: Engine) -> SqlUsersRepo:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    return SqlUsersRepo(engine)


@pytest.fixture()
def repo(engine: Engine, users: SqlUsersRepo) -> SqlResetRepo:
    return SqlResetRepo(engine)


def make_user(users: SqlUsersRepo, email: str = "ada@example.com") -> str:
    return users.create_user(email, OLD_HASH).id


def add_session(users: SqlUsersRepo, user_id: str, token: str) -> None:
    users.create_session(user_id, token, NOW, NOW + timedelta(days=7))


def rows(engine: Engine) -> list[tuple[str, str, int]]:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT user_id::text, code_hash, attempts FROM password_resets")
        )
        return [(r[0], r[1], r[2]) for r in result]


def scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


# ---- issue / discard / delete_expired --------------------------------------------
def test_issue_stores_one_row_per_user_and_a_newer_code_replaces_it(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    repo.issue(uid, "hash-1", LATER, NOW)
    assert repo.claim_attempt(uid, NOW, 5) == "hash-1"
    assert rows(engine) == [(uid, "hash-1", 1)]  # one attempt counted

    repo.issue(uid, "hash-2", LATER, NOW)  # a newer request
    assert rows(engine) == [(uid, "hash-2", 0)]  # replaced, attempts back to 0


def test_two_users_have_two_rows(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    a, b = make_user(users, "a@example.com"), make_user(users, "b@example.com")
    repo.issue(a, "ha", LATER, NOW)
    repo.issue(b, "hb", LATER, NOW)
    assert sorted(r[1] for r in rows(engine)) == ["ha", "hb"]


def test_discard_removes_only_that_exact_code(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    repo.issue(uid, "hash-1", LATER, NOW)
    assert repo.discard(uid, "some-other-hash") is False
    assert len(rows(engine)) == 1
    assert repo.discard(uid, "hash-1") is True
    assert rows(engine) == []
    assert repo.discard(uid, "hash-1") is False


def test_delete_expired_removes_only_rows_past_their_expiry(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    old, fresh = make_user(users, "o@example.com"), make_user(users, "f@example.com")
    repo.issue(old, "ho", NOW - timedelta(minutes=1), NOW - timedelta(minutes=16))
    repo.issue(fresh, "hf", LATER, NOW)
    assert repo.delete_expired(NOW) == 1
    assert [r[1] for r in rows(engine)] == ["hf"]


# ---- claim_attempt ----------------------------------------------------------------
def test_each_claim_counts_one_attempt_and_stops_at_the_cap(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    repo.issue(uid, "hash-1", LATER, NOW)
    assert [repo.claim_attempt(uid, NOW, 5) for _ in range(5)] == ["hash-1"] * 5
    assert repo.claim_attempt(uid, NOW, 5) is None  # the sixth is refused
    assert rows(engine) == [(uid, "hash-1", 5)]  # and not counted


def test_a_claim_is_refused_after_expiry_and_without_a_row(
    repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    assert repo.claim_attempt(uid, NOW, 5) is None  # no row
    repo.issue(uid, "hash-1", LATER, NOW)
    assert repo.claim_attempt(uid, LATER, 5) is None  # exactly at the expiry
    assert repo.claim_attempt(uid, LATER + timedelta(seconds=1), 5) is None
    assert repo.claim_attempt(uid, LATER - timedelta(seconds=1), 5) == "hash-1"


def test_parallel_claims_cannot_exceed_the_cap(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    repo.issue(uid, "hash-1", LATER, NOW)
    barrier = threading.Barrier(12)
    got: list[str | None] = [None] * 12

    def claim(i: int) -> None:
        barrier.wait()
        got[i] = repo.claim_attempt(uid, NOW, 5)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for g in got if g is not None) == 5
    assert rows(engine)[0][2] == 5


# ---- complete ---------------------------------------------------------------------
def test_complete_sets_the_password_deletes_the_code_and_ends_only_that_users_sessions(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    ada, bob = make_user(users, "ada@example.com"), make_user(users, "bob@example.com")
    add_session(users, ada, "ada-1")
    add_session(users, ada, "ada-2")
    add_session(users, bob, "bob-1")
    repo.issue(ada, "hash-1", LATER, NOW)
    repo.issue(bob, "hash-b", LATER, NOW)

    assert repo.complete(ada, "hash-1", NEW_HASH) is True

    assert (
        scalar(engine, "SELECT password_hash FROM users WHERE id = :u", u=ada)
        == NEW_HASH
    )
    assert (
        scalar(engine, "SELECT password_hash FROM users WHERE id = :u", u=bob)
        == OLD_HASH
    )
    assert (
        scalar(engine, "SELECT count(*) FROM sessions WHERE user_id = :u", u=ada) == 0
    )
    assert (
        scalar(engine, "SELECT count(*) FROM sessions WHERE user_id = :u", u=bob) == 1
    )
    assert [r[0] for r in rows(engine)] == [bob]  # ada's code is gone, bob's stays


def test_complete_changes_nothing_when_the_code_is_gone_or_different(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    add_session(users, uid, "s-1")
    assert repo.complete(uid, "hash-1", NEW_HASH) is False  # no row at all
    repo.issue(uid, "hash-1", LATER, NOW)
    assert repo.complete(uid, "not-the-stored-hash", NEW_HASH) is False
    assert (
        scalar(engine, "SELECT password_hash FROM users WHERE id = :u", u=uid)
        == OLD_HASH
    )
    assert (
        scalar(engine, "SELECT count(*) FROM sessions WHERE user_id = :u", u=uid) == 1
    )
    assert len(rows(engine)) == 1  # the code is still there


def test_two_threads_completing_the_same_code_give_exactly_one_success(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    add_session(users, uid, "s-1")
    repo.issue(uid, "hash-1", LATER, NOW)
    barrier = threading.Barrier(2)
    outcomes: list[bool | None] = [None, None]

    def run(i: int) -> None:
        barrier.wait()
        outcomes[i] = repo.complete(uid, "hash-1", f"password-from-thread-{i}")

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(o for o in outcomes if o is not None) == [False, True]
    winner = outcomes.index(True)
    assert (
        scalar(engine, "SELECT password_hash FROM users WHERE id = :u", u=uid)
        == f"password-from-thread-{winner}"
    )


# ---- cascade and bad input ----------------------------------------------------------
def test_deleting_the_user_removes_the_open_code(
    engine: Engine, repo: SqlResetRepo, users: SqlUsersRepo
) -> None:
    uid = make_user(users)
    repo.issue(uid, "hash-1", LATER, NOW)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    assert rows(engine) == []


def test_a_malformed_user_id_is_handled_without_an_error(
    engine: Engine, repo: SqlResetRepo
) -> None:
    repo.issue("not-a-uuid", "hash-1", LATER, NOW)  # nothing stored, nothing raised
    assert repo.claim_attempt("not-a-uuid", NOW, 5) is None
    assert repo.discard("not-a-uuid", "hash-1") is False
    assert repo.complete("not-a-uuid", "hash-1", NEW_HASH) is False
    assert rows(engine) == []
