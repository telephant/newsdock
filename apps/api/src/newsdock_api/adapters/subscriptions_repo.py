"""Subscription persistence (role: api_rw): parameterized ORM queries only."""

from newsdock_db.models import Agent as AgentRow
from newsdock_db.models import Subscription
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from newsdock_api.adapters.agent_scope import visible
from newsdock_api.adapters.ids import as_uuid
from newsdock_api.domain.agents import AgentScope
from newsdock_api.domain.subscriptions import AdminSubscription, SubscriptionRecord


def _record(row: Subscription) -> SubscriptionRecord:
    return SubscriptionRecord(
        id=str(row.id),
        agent_id=str(row.agent_id),
        filter=dict(row.filter),
        created_at=row.created_at,
    )


class SqlSubscriptionsRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, agent_id: str, filter_json: dict[str, str]) -> SubscriptionRecord:
        with Session(self._engine) as session:
            row = Subscription(agent_id=agent_id, filter=filter_json)
            session.add(row)
            session.commit()
            session.refresh(row)
            return _record(row)

    def list_own(self, agent_id: str) -> list[SubscriptionRecord]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(Subscription)
                .where(Subscription.agent_id == agent_id)
                .order_by(Subscription.created_at, Subscription.id)
            )
            return [_record(r) for r in rows]

    def get_own(self, agent_id: str, sub_id: str) -> SubscriptionRecord | None:
        key = as_uuid(sub_id)
        if key is None:
            return None
        with Session(self._engine) as session:
            row = session.scalar(
                select(Subscription).where(
                    Subscription.id == key, Subscription.agent_id == agent_id
                )
            )
            return _record(row) if row else None

    def delete_own(self, agent_id: str, sub_id: str) -> bool:
        key = as_uuid(sub_id)
        if key is None:
            return False
        with Session(self._engine) as session:
            result = session.execute(
                delete(Subscription).where(
                    Subscription.id == key, Subscription.agent_id == agent_id
                )
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    def delete_visible(self, sub_id: str, scope: AgentScope) -> bool:
        """Delete a subscription of any agent the scope may see (ADR-0023)."""
        key = as_uuid(sub_id)
        if key is None:
            return False
        with Session(self._engine) as session:
            result = session.execute(
                delete(Subscription).where(
                    Subscription.id == key,
                    Subscription.agent_id.in_(
                        select(AgentRow.id).where(visible(scope))
                    ),
                )
            )
            session.commit()
            return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]

    def count_own(self, agent_id: str) -> int:
        with Session(self._engine) as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(Subscription)
                    .where(Subscription.agent_id == agent_id)
                )
                or 0
            )

    def exists(self, sub_id: str) -> bool:
        key = as_uuid(sub_id)
        if key is None:
            return False
        with Session(self._engine) as session:
            return (
                session.scalar(select(Subscription.id).where(Subscription.id == key))
                is not None
            )

    def list_visible(self, scope: AgentScope) -> list[AdminSubscription]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(Subscription, AgentRow.name)
                .join(AgentRow, AgentRow.id == Subscription.agent_id)
                .where(visible(scope))
                .order_by(Subscription.created_at, Subscription.id)
            ).all()
            return [
                AdminSubscription(**_record(sub).model_dump(), agent_name=name)
                for sub, name in rows
            ]
