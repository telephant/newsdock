"""The one SQL predicate behind agent ownership (ADR-0023): parameterized, no I/O.

Both repos build every agent and subscription query through `visible`, so a scope
cannot be forgotten or applied differently in two places.
"""

from newsdock_db.models import Agent as AgentRow
from sqlalchemy import ColumnElement, false, true

from newsdock_api.domain.agents import AgentScope


def visible(scope: AgentScope) -> ColumnElement[bool]:
    """Rows of `agents` the scope may see.

    The full scope matches every agent, including ones with no owner. An own scope
    matches `owner_id = <me>`; one that somehow has no user id matches nothing
    (never `owner_id IS NULL`, which would expose ownerless agents).
    """
    if scope.everything:
        return true()
    if scope.owner_id is None:
        return false()
    return AgentRow.owner_id == scope.owner_id
