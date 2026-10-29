"""Password reset by emailed code: the pure rules (spec forgot-password, design C-41).

A code is six digits from the `secrets` module. Only a keyed hash of it is stored:
`HMAC-SHA256(secret, "<user_id>:<code>")`, so a leaked table is useless without the
server secret and a row cannot be replayed for another user (ADR-0026). No I/O here;
the store behind `ResetStore` is `adapters/reset_repo.py`.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import Protocol

CODE_LENGTH = 6
# ASCII digits only and no trailing newline: `\d` would accept other scripts' digits
# and `$` a final "\n", so the pattern is used with `fullmatch`.
CODE_PATTERN = re.compile(r"[0-9]{6}")
# Unknown emails and missing rows are compared against this id so the work, and the
# time it takes, looks like a real check.
DUMMY_USER_ID = "00000000-0000-0000-0000-000000000000"

MAIL_SUBJECT = "newsdock: your password reset code"


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(secret: str, user_id: str, code: str) -> str:
    message = f"{user_id}:{code}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def matches(stored: str, secret: str, user_id: str, code: str) -> bool:
    """Constant-time check of `code` against a stored hash; never raises."""
    if not stored.isascii():  # compare_digest refuses non-ASCII strings
        return False
    return hmac.compare_digest(stored, hash_code(secret, user_id, code))


def code_expiry(now: datetime, minutes: int) -> datetime:
    return now + timedelta(minutes=minutes)


def reset_mail(code: str, minutes: int) -> tuple[str, str]:
    """Subject and plain-text body. No link, no address, no user name."""
    unit = "minute" if minutes == 1 else "minutes"
    body = (
        f"Your newsdock password reset code is: {code}\n"
        "\n"
        f"It is valid for {minutes} {unit}. Enter it on the reset page together "
        "with your new password.\n"
        "\n"
        "If you did not ask for this, you can ignore this message; "
        "your password has not changed.\n"
    )
    return MAIL_SUBJECT, body


class ResetStore(Protocol):
    """Open reset codes, one per user (implemented by `SqlResetRepo`)."""

    def issue(
        self, user_id: str, code_hash: str, expires_at: datetime, now: datetime
    ) -> None:
        """Store the hash, replacing any older code of the user (attempts back to 0)."""
        ...

    def discard(self, user_id: str, code_hash: str) -> bool:
        """Remove that exact code (an unsent one); False when it is not there."""
        ...

    def delete_expired(self, now: datetime) -> int: ...

    def claim_attempt(
        self, user_id: str, now: datetime, max_attempts: int
    ) -> str | None:
        """Count one attempt and return the stored hash, or None when the user has no
        open, unexpired code with attempts left."""
        ...

    def complete(self, user_id: str, code_hash: str, new_password_hash: str) -> bool:
        """In one transaction: delete the code, set the password hash and end the
        user's sessions. False (and nothing changed) when the code is already gone."""
        ...
