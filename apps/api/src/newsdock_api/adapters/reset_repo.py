"""Password reset codes (role: api_rw): parameterized ORM statements only.

One open code per user. `claim_attempt` counts the attempt in the same statement that
reads the hash, so parallel guesses cannot exceed the cap; `complete` deletes the code,
sets the password and ends the user's sessions in one transaction, so a code works once
even when two requests race (the second DELETE finds no row). ADR-0026, design C-42.
"""

from datetime import datetime
from typing import Any

from newsdock_db.models import PasswordReset, User, UserSession
from sqlalchemy import Engine, delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from newsdock_api.adapters.ids import as_uuid


def _rowcount(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


class SqlResetRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def issue(
        self, user_id: str, code_hash: str, expires_at: datetime, now: datetime
    ) -> None:
        key = as_uuid(user_id)
        if key is None:
            return
        statement = insert(PasswordReset).values(
            user_id=key,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            created_at=now,
        )
        statement = statement.on_conflict_do_update(  # a newer request replaces
            index_elements=["user_id"],
            set_={
                "code_hash": code_hash,
                "expires_at": expires_at,
                "attempts": 0,
                "created_at": now,
            },
        )
        with Session(self._engine) as session, session.begin():
            session.execute(statement)

    def discard(self, user_id: str, code_hash: str) -> bool:
        key = as_uuid(user_id)
        if key is None:
            return False
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                delete(PasswordReset).where(
                    PasswordReset.user_id == key, PasswordReset.code_hash == code_hash
                )
            )
            return _rowcount(result) > 0

    def delete_expired(self, now: datetime) -> int:
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                delete(PasswordReset).where(PasswordReset.expires_at < now)
            )
            return _rowcount(result)

    def claim_attempt(
        self, user_id: str, now: datetime, max_attempts: int
    ) -> str | None:
        key = as_uuid(user_id)
        if key is None:
            return None
        statement = (
            update(PasswordReset)
            .where(
                PasswordReset.user_id == key,
                PasswordReset.expires_at > now,
                PasswordReset.attempts < max_attempts,
            )
            .values(attempts=PasswordReset.attempts + 1)
            .returning(PasswordReset.code_hash)
        )
        with Session(self._engine) as session, session.begin():
            return session.execute(statement).scalar_one_or_none()

    def complete(self, user_id: str, code_hash: str, new_password_hash: str) -> bool:
        key = as_uuid(user_id)
        if key is None:
            return False
        with Session(self._engine) as session, session.begin():
            claimed = session.execute(
                delete(PasswordReset).where(
                    PasswordReset.user_id == key, PasswordReset.code_hash == code_hash
                )
            )
            if _rowcount(claimed) != 1:
                return False  # already used, replaced, expired away or never there
            session.execute(
                update(User)
                .where(User.id == key)
                .values(password_hash=new_password_hash)
            )
            session.execute(delete(UserSession).where(UserSession.user_id == key))
            return True
