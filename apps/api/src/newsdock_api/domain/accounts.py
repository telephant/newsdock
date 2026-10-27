"""Human accounts: roles, permissions, input policy, login and session rules (ADR-0020).

Pure, no I/O. Hashing is a port (`PasswordHasher`): the argon2 adapter lives in
`adapters/passwords.py`. Nothing here logs or returns a password or a hash.
"""

import re
from datetime import datetime, timedelta
from enum import StrEnum
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict

EMAIL_MAX_LENGTH = 254
PASSWORD_MAX_LENGTH = 128
TOUCH_INTERVAL = timedelta(seconds=60)  # `last_seen_at` is refreshed at most this often
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"


# The one permission table (design-detail §2); routes ask for a permission.
PERMISSIONS: dict[str, frozenset[Role]] = {
    "read_articles": frozenset({Role.OWNER, Role.ADMIN, Role.VIEWER}),
    "live_feed": frozenset({Role.OWNER, Role.ADMIN, Role.VIEWER}),
    "manage_agents": frozenset({Role.OWNER, Role.ADMIN}),
    "manage_users": frozenset({Role.OWNER}),
}


def can(role: Role, permission: str) -> bool:
    """True if `role` holds `permission`; an unknown permission raises KeyError."""
    return role in PERMISSIONS[permission]


class InvalidEmail(ValueError):
    pass


class WeakPassword(ValueError):
    pass


class SignupClosed(Exception):
    pass


class InvalidCredentials(Exception):
    """One error for an unknown email and a wrong password (AC-5)."""

    def __init__(self) -> None:
        super().__init__("invalid_credentials")


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.match(email):
        raise InvalidEmail("invalid_email")
    return email


def check_password(password: str, *, min_length: int) -> None:
    """Length is the only rule; the string is never trimmed or altered."""
    if not min_length <= len(password) <= PASSWORD_MAX_LENGTH:
        raise WeakPassword("invalid_password_length")


def ensure_signup_open(signup_open: bool) -> None:
    if not signup_open:
        raise SignupClosed("signup_closed")


class DuplicateEmail(Exception):
    pass


class LastOwner(Exception):
    """A change that would leave the system without an owner (AC-10)."""


class UserSummary(BaseModel):
    """A user as listed to an owner: never carries the hash."""

    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    role: Role
    created_at: datetime


class SessionInfo(BaseModel):
    """A live session joined with its user; the role is the current one."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
    role: Role
    last_seen_at: datetime
    expires_at: datetime


class StoredUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    role: Role
    password_hash: str


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, stored: str, password: str) -> bool:
        """False for a wrong password or an unreadable hash; never raises."""
        ...

    def needs_rehash(self, stored: str) -> bool: ...


class UserLookup(Protocol):
    def find_by_email(self, email: str) -> StoredUser | None: ...


class LoginResult(NamedTuple):
    user: StoredUser
    rehash: bool  # the stored hash uses weaker parameters than today's


def verify_login(
    users: UserLookup,
    hasher: PasswordHasher,
    email: str,
    password: str,
    dummy_hash: str,
) -> LoginResult:
    """Check credentials with equal work for known and unknown emails (AC-5).

    An unknown or malformed email is verified against `dummy_hash` so neither the
    result nor the time says whether the account exists.
    """
    try:
        user = users.find_by_email(normalize_email(email))
    except InvalidEmail:
        user = None
    matched = hasher.verify(user.password_hash if user else dummy_hash, password)
    if user is None or not matched:
        raise InvalidCredentials
    return LoginResult(user, hasher.needs_rehash(user.password_hash))


def session_expiry(created_at: datetime, absolute: timedelta) -> datetime:
    return created_at + absolute


def session_valid(
    now: datetime, *, last_seen_at: datetime, expires_at: datetime, idle: timedelta
) -> bool:
    """Alive while before the absolute expiry and not idle longer than `idle`."""
    return now < expires_at and now - last_seen_at <= idle


def should_touch(now: datetime, last_seen_at: datetime) -> bool:
    return now - last_seen_at >= TOUCH_INTERVAL
