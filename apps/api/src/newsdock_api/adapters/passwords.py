"""Password hashing with argon2id (ADR-0020): the adapter behind `PasswordHasher`.

argon2-cffi defaults are used as is (argon2id v19, t=3, m=64 MiB, p=4); on the dev
machine one hash takes about 23 ms (T-01). Passwords are never logged or returned.
"""

import secrets

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from newsdock_api.domain.accounts import PasswordHasher


class Argon2Hasher:
    def __init__(self) -> None:
        self._hasher = _Argon2()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, stored: str, password: str) -> bool:
        try:
            return self._hasher.verify(stored, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, stored: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(stored)
        except InvalidHashError:
            return False


def make_dummy_hash(hasher: PasswordHasher) -> str:
    """A valid hash of a random password nobody knows, for equal-work failures."""
    return hasher.hash(secrets.token_urlsafe(24))
