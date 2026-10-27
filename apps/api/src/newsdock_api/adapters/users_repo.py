"""Users and sessions persistence (role: api_rw): parameterized ORM queries only.

Every write that depends on "how many owners exist" (first sign-up, role change,
delete) first takes one Postgres advisory transaction lock, so two racing requests
cannot both become the first owner or both remove the last one (design-detail §3).
The lock is released at commit or rollback.
"""

from datetime import datetime, timedelta

from newsdock_db.models import User, UserSession
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsdock_api.adapters.ids import as_uuid
from newsdock_api.domain.accounts import (
    DuplicateEmail,
    LastOwner,
    Role,
    SessionInfo,
    StoredUser,
    UserSummary,
)

USERS_WRITE_LOCK = 7_041_001  # one constant: "decides who the owners are"


def _stored(row: User) -> StoredUser:
    return StoredUser(
        id=str(row.id),
        email=row.email,
        role=Role(row.role),
        password_hash=row.password_hash,
    )


def _lock(session: Session) -> None:
    session.execute(select(func.pg_advisory_xact_lock(USERS_WRITE_LOCK)))


def _owner_count(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(User).where(User.role == Role.OWNER.value)
        )
        or 0
    )


class SqlUsersRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- users ----------------------------------------------------------------
    def create_user(self, email: str, password_hash: str) -> StoredUser:
        """Insert a user; the very first account becomes the owner, the rest viewers."""
        try:
            with Session(self._engine) as session, session.begin():
                _lock(session)
                first = session.scalar(select(func.count()).select_from(User)) == 0
                row = User(
                    email=email,
                    password_hash=password_hash,
                    role=(Role.OWNER if first else Role.VIEWER).value,
                )
                session.add(row)
                session.flush()
                return _stored(row)
        except IntegrityError as exc:
            raise DuplicateEmail(email) from exc

    def find_by_email(self, email: str) -> StoredUser | None:
        with Session(self._engine) as session:
            row = session.scalar(select(User).where(User.email == email))
            return _stored(row) if row else None

    def get_by_id(self, user_id: str) -> StoredUser | None:
        key = as_uuid(user_id)
        if key is None:
            return None
        with Session(self._engine) as session:
            row = session.get(User, key)
            return _stored(row) if row else None

    def list_users(self) -> list[UserSummary]:
        with Session(self._engine) as session:
            rows = session.scalars(select(User).order_by(User.created_at, User.id))
            return [
                UserSummary(
                    id=str(r.id),
                    email=r.email,
                    role=Role(r.role),
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def set_password_hash(self, user_id: str, password_hash: str) -> bool:
        key = as_uuid(user_id)
        if key is None:
            return False
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                update(User).where(User.id == key).values(password_hash=password_hash)
            )
            return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    def set_role(self, user_id: str, role: Role) -> bool:
        """False if the user is absent; LastOwner if it would drop the last owner."""
        key = as_uuid(user_id)
        if key is None:
            return False
        with Session(self._engine) as session, session.begin():
            _lock(session)
            row = session.get(User, key)
            if row is None:
                return False
            if (
                row.role == Role.OWNER.value
                and role is not Role.OWNER
                and _owner_count(session) <= 1
            ):
                raise LastOwner(user_id)
            row.role = role.value
            return True

    def delete_user(self, user_id: str) -> bool:
        """Delete a user (their sessions cascade); same last-owner rule as set_role."""
        key = as_uuid(user_id)
        if key is None:
            return False
        with Session(self._engine) as session, session.begin():
            _lock(session)
            row = session.get(User, key)
            if row is None:
                return False
            if row.role == Role.OWNER.value and _owner_count(session) <= 1:
                raise LastOwner(user_id)
            session.delete(row)
            return True

    # ---- sessions -------------------------------------------------------------
    def create_session(
        self, user_id: str, token_hash: str, now: datetime, expires_at: datetime
    ) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(
                UserSession(
                    token_hash=token_hash,
                    user_id=user_id,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=expires_at,
                )
            )

    def find_session(self, token_hash: str) -> SessionInfo | None:
        with Session(self._engine) as session:
            row = session.execute(
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(UserSession.token_hash == token_hash)
            ).first()
            if row is None:
                return None
            sess, user = row
            return SessionInfo(
                user_id=str(user.id),
                email=user.email,
                role=Role(user.role),
                last_seen_at=sess.last_seen_at,
                expires_at=sess.expires_at,
            )

    def touch_session(self, token_hash: str, now: datetime) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(UserSession)
                .where(UserSession.token_hash == token_hash)
                .values(last_seen_at=now)
            )

    def delete_session(self, token_hash: str) -> bool:
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                delete(UserSession).where(UserSession.token_hash == token_hash)
            )
            return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    def delete_user_sessions(self, user_id: str) -> int:
        key = as_uuid(user_id)
        if key is None:
            return 0
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                delete(UserSession).where(UserSession.user_id == key)
            )
            return int(result.rowcount)  # type: ignore[attr-defined]

    def delete_expired(self, now: datetime, idle: timedelta) -> int:
        """Remove sessions past their absolute expiry or idle longer than `idle`."""
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                delete(UserSession).where(
                    (UserSession.expires_at <= now)
                    | (UserSession.last_seen_at < now - idle)
                )
            )
            return int(result.rowcount)  # type: ignore[attr-defined]
