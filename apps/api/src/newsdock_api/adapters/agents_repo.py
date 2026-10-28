"""Agent registry persistence (role: api_rw): parameterized ORM queries only."""

from datetime import datetime, timedelta

from newsdock_db.models import Agent as AgentRow
from newsdock_db.models import AgentCursor, ApiKey, User
from sqlalchemy import Engine, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsdock_api.adapters.agent_scope import visible
from newsdock_api.adapters.ids import as_uuid
from newsdock_api.domain.agents import (
    AgentScope,
    AgentSummary,
    GeneratedKey,
    KeySummary,
    RegisteredAgent,
    StoredKey,
)

TOUCH_INTERVAL = timedelta(minutes=1)  # last_used_at is written at most this often


class DuplicateAgentError(Exception):
    """An agent with this name already exists."""


class SqlAgentsRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_agent(
        self, name: str, key: GeneratedKey, owner_id: str | None
    ) -> RegisteredAgent:
        """`owner_id` is the creating user, or None for CLI/admin-token agents."""
        with Session(self._engine) as session:
            agent = AgentRow(name=name, owner_id=owner_id)
            session.add(agent)
            try:
                session.flush()
            except IntegrityError as exc:
                raise DuplicateAgentError(name) from exc
            key_row = ApiKey(
                agent_id=agent.id, prefix=key.prefix, key_hash=key.key_hash
            )
            session.add(key_row)
            session.commit()
            return RegisteredAgent(
                id=str(agent.id), name=agent.name, key_id=str(key_row.id)
            )

    def agent_visible(self, agent_id: str, scope: AgentScope) -> bool:
        if as_uuid(agent_id) is None:
            return False
        with Session(self._engine) as session:
            return (
                session.scalar(
                    select(AgentRow.id).where(AgentRow.id == agent_id, visible(scope))
                )
                is not None
            )

    def add_key(
        self, agent_id: str, key: GeneratedKey, scope: AgentScope
    ) -> str | None:
        """The new key's id, or None when the agent is not visible to `scope`."""
        if as_uuid(agent_id) is None:
            return None
        with Session(self._engine) as session:
            found = session.scalar(
                select(AgentRow.id).where(AgentRow.id == agent_id, visible(scope))
            )
            if found is None:
                return None
            row = ApiKey(agent_id=agent_id, prefix=key.prefix, key_hash=key.key_hash)
            session.add(row)
            session.commit()
            return str(row.id)

    def revoke_key(self, agent_id: str, key_id: str, scope: AgentScope) -> bool:
        if as_uuid(agent_id) is None or as_uuid(key_id) is None:
            return False
        with Session(self._engine) as session:
            result = session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id, ApiKey.agent_id == agent_id)
                .where(ApiKey.revoked_at.is_(None))
                .where(
                    ApiKey.agent_id.in_(
                        select(AgentRow.id).where(
                            AgentRow.id == agent_id, visible(scope)
                        )
                    )
                )
                .values(revoked_at=func.now())
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    def set_status(self, agent_id: str, status: str, scope: AgentScope) -> bool:
        if as_uuid(agent_id) is None:
            return False
        with Session(self._engine) as session:
            result = session.execute(
                update(AgentRow)
                .where(AgentRow.id == agent_id, visible(scope))
                .values(status=status)
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    def list_agents(self, scope: AgentScope) -> list[AgentSummary]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(AgentRow, User.email)
                .outerjoin(User, User.id == AgentRow.owner_id)
                .where(visible(scope))
                .order_by(AgentRow.created_at)
            ).all()
            ids = [a.id for a, _ in rows]
            keys = session.scalars(
                select(ApiKey)
                .where(ApiKey.agent_id.in_(ids))
                .order_by(ApiKey.created_at)
            ).all()
            by_agent: dict[str, list[KeySummary]] = {}
            for k in keys:
                by_agent.setdefault(str(k.agent_id), []).append(
                    KeySummary(
                        key_id=str(k.id),
                        prefix=k.prefix,
                        created_at=k.created_at,
                        revoked_at=k.revoked_at,
                        last_used_at=k.last_used_at,
                    )
                )
            return [
                AgentSummary(
                    agent_id=str(a.id),
                    name=a.name,
                    status=a.status,
                    keys=by_agent.get(str(a.id), []),
                    owner_id=str(a.owner_id) if a.owner_id else None,
                    owner_email=email,
                )
                for a, email in rows
            ]

    def find_key(self, prefix: str) -> StoredKey | None:
        with Session(self._engine) as session:
            row = session.execute(
                select(ApiKey, AgentRow)
                .join(AgentRow, AgentRow.id == ApiKey.agent_id)
                .where(ApiKey.prefix == prefix)
            ).first()
            if row is None:
                return None
            key, agent = row
            return StoredKey(
                key_id=str(key.id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                key_hash=key.key_hash,
                revoked=key.revoked_at is not None,
                agent_active=agent.status == "active",
            )

    def key_usable(self, key_id: str) -> bool:
        """True while the key is not revoked and its agent is active (AC-11)."""
        key = as_uuid(key_id)
        if key is None:
            return False
        with Session(self._engine) as session:
            row = session.execute(
                select(ApiKey.revoked_at, AgentRow.status)
                .join(AgentRow, AgentRow.id == ApiKey.agent_id)
                .where(ApiKey.id == key)
            ).first()
            return row is not None and row[0] is None and row[1] == "active"

    def touch_key(self, key_id: str, now: datetime) -> None:
        with Session(self._engine) as session:
            session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .where(
                    or_(
                        ApiKey.last_used_at.is_(None),
                        ApiKey.last_used_at < now - TOUCH_INTERVAL,
                    )
                )
                .values(last_used_at=now)
            )
            session.commit()

    def get_cursor(self, agent_id: str) -> int | None:
        with Session(self._engine) as session:
            return session.scalar(
                select(AgentCursor.seq).where(AgentCursor.agent_id == agent_id)
            )

    def advance_cursor(self, agent_id: str, seq: int) -> int:
        """Forward-only and idempotent (ADR-0017): returns the stored position."""
        upsert = insert(AgentCursor).values(agent_id=agent_id, seq=seq)
        statement = upsert.on_conflict_do_update(
            index_elements=[AgentCursor.agent_id],
            set_={
                "seq": func.greatest(AgentCursor.seq, upsert.excluded.seq),
                "updated_at": func.now(),
            },
        ).returning(AgentCursor.seq)
        with Session(self._engine) as session:
            stored = session.execute(statement).scalar_one()
            session.commit()
            return int(stored)
