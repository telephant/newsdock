"""TC-6, TC-11, TC-13, TC-23: account rules are pure (AC-3, AC-5, AC-6, AC-9)."""

from datetime import UTC, datetime, timedelta

import pytest
from newsdock_api.domain.accounts import (
    PERMISSIONS,
    InvalidCredentials,
    InvalidEmail,
    Role,
    SignupClosed,
    StoredUser,
    WeakPassword,
    can,
    check_password,
    ensure_signup_open,
    normalize_email,
    session_expiry,
    session_valid,
    should_touch,
    verify_login,
)

NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
IDLE = timedelta(hours=12)


# --- TC-6: policy -----------------------------------------------------------


def test_email_is_trimmed_and_lower_cased() -> None:
    assert normalize_email("  A@X.IO ") == "a@x.io"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "no-at-sign",
        "a@b",
        "a b@x.io",
        "@x.io",
        "a@",
        "a@@x.io",
        "x" * 250 + "@x.io",
    ],
)
def test_malformed_or_overlong_email_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidEmail):
        normalize_email(raw)


def test_password_length_bounds() -> None:
    check_password("x" * 10, min_length=10)
    check_password("x" * 128, min_length=10)
    with pytest.raises(WeakPassword):
        check_password("x" * 9, min_length=10)
    with pytest.raises(WeakPassword):
        check_password("x" * 129, min_length=10)


def test_password_is_not_trimmed_or_altered() -> None:
    check_password(" " * 10, min_length=10)  # spaces count; no silent stripping


def test_signup_closed_raises() -> None:
    ensure_signup_open(True)
    with pytest.raises(SignupClosed):
        ensure_signup_open(False)


# --- TC-23: permissions -----------------------------------------------------


def test_permission_table() -> None:
    every = {Role.OWNER, Role.ADMIN, Role.VIEWER}
    assert PERMISSIONS["read_articles"] == every
    assert PERMISSIONS["live_feed"] == every
    assert PERMISSIONS["manage_agents"] == {Role.OWNER, Role.ADMIN}
    assert PERMISSIONS["manage_users"] == {Role.OWNER}


def test_can_follows_the_table() -> None:
    assert can(Role.VIEWER, "read_articles")
    assert not can(Role.VIEWER, "manage_agents")
    assert can(Role.ADMIN, "manage_agents")
    assert not can(Role.ADMIN, "manage_users")
    assert can(Role.OWNER, "manage_users")


def test_unknown_permission_raises() -> None:
    with pytest.raises(KeyError):
        can(Role.OWNER, "launch_rockets")


# --- TC-11: verify_login ----------------------------------------------------


class FakeHasher:
    """Hash is 'h:' + password; counts verify calls and records the hashes used."""

    def __init__(self) -> None:
        self.verified: list[str] = []

    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, stored: str, password: str) -> bool:
        self.verified.append(stored)
        return stored == f"h:{password}"

    def needs_rehash(self, stored: str) -> bool:
        return stored.endswith("old")


class FakeUsers:
    def __init__(self, *users: StoredUser) -> None:
        self._by_email = {u.email: u for u in users}

    def find_by_email(self, email: str) -> StoredUser | None:
        return self._by_email.get(email)


ALICE = StoredUser(
    id="u1", email="a@x.io", role=Role.VIEWER, password_hash="h:secret-pass"
)
DUMMY = "h:dummy-never-matches"


def test_right_password_returns_the_user() -> None:
    hasher = FakeHasher()
    result = verify_login(FakeUsers(ALICE), hasher, "A@x.io ", "secret-pass", DUMMY)
    assert result.user == ALICE
    assert result.rehash is False


def test_rehash_flag_follows_the_hasher() -> None:
    old = StoredUser(
        id="u2", email="o@x.io", role=Role.VIEWER, password_hash="h:pw-old"
    )
    result = verify_login(FakeUsers(old), FakeHasher(), "o@x.io", "pw-old", DUMMY)
    assert result.rehash is True


def test_unknown_email_still_verifies_against_the_dummy_hash() -> None:
    hasher = FakeHasher()
    with pytest.raises(InvalidCredentials):
        verify_login(FakeUsers(ALICE), hasher, "nobody@x.io", "whatever-123", DUMMY)
    assert hasher.verified == [DUMMY]  # equal work, no early exit (AC-5)


def test_malformed_email_also_does_equal_work() -> None:
    hasher = FakeHasher()
    with pytest.raises(InvalidCredentials):
        verify_login(FakeUsers(ALICE), hasher, "not an email", "whatever-123", DUMMY)
    assert hasher.verified == [DUMMY]


def test_wrong_password_and_unknown_email_raise_the_same_error() -> None:
    hasher = FakeHasher()
    errors = []
    for email in ("a@x.io", "nobody@x.io"):
        with pytest.raises(InvalidCredentials) as caught:
            verify_login(FakeUsers(ALICE), hasher, email, "wrong-password", DUMMY)
        errors.append((type(caught.value), str(caught.value), caught.value.args))
    assert errors[0] == errors[1]


def test_dummy_password_cannot_log_in_as_anyone() -> None:
    with pytest.raises(InvalidCredentials):
        verify_login(
            FakeUsers(ALICE), FakeHasher(), "a@x.io", "dummy-never-matches", DUMMY
        )


# --- TC-13: session validity -----------------------------------------------


def test_session_expiry_adds_the_absolute_lifetime() -> None:
    assert session_expiry(NOW, timedelta(days=7)) == NOW + timedelta(days=7)


def test_session_valid_inside_both_limits() -> None:
    assert session_valid(
        NOW,
        last_seen_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=1),
        idle=IDLE,
    )


def test_session_invalid_after_idle_limit() -> None:
    expires = NOW + timedelta(days=1)
    assert not session_valid(
        NOW,
        last_seen_at=NOW - IDLE - timedelta(seconds=1),
        expires_at=expires,
        idle=IDLE,
    )


def test_session_invalid_at_or_after_absolute_expiry() -> None:
    seen = NOW - timedelta(minutes=1)
    assert not session_valid(
        NOW, last_seen_at=seen, expires_at=NOW, idle=IDLE
    )  # boundary: expired
    assert not session_valid(
        NOW, last_seen_at=seen, expires_at=NOW - timedelta(seconds=1), idle=IDLE
    )
    assert session_valid(
        NOW, last_seen_at=seen, expires_at=NOW + timedelta(seconds=1), idle=IDLE
    )


def test_idle_boundary_is_still_valid_exactly_at_the_limit() -> None:
    assert session_valid(
        NOW, last_seen_at=NOW - IDLE, expires_at=NOW + timedelta(days=1), idle=IDLE
    )


def test_touch_is_skipped_when_last_seen_is_recent() -> None:
    assert not should_touch(NOW, NOW - timedelta(seconds=59))
    assert should_touch(NOW, NOW - timedelta(seconds=60))
    assert should_touch(NOW, NOW - timedelta(hours=1))
