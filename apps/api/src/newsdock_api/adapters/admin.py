"""Admin routes under /api/admin: manage agents, their keys and subscriptions.

Guarded by `require_admin` (adapters/principal.py): the admin token (CLI) or a
session whose role may manage agents (admin, owner). An agent key is a different
credential and gets 403; no credential gets 401. Plaintext keys appear in a
response exactly once, when issued.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from newsdock_api.adapters.agents_repo import DuplicateAgentError
from newsdock_api.domain.accounts import Principal
from newsdock_api.domain.agents import (
    AgentRegistry,
    AgentSummary,
    make_key,
)
from newsdock_api.domain.subscriptions import AdminSubscription, SubscriptionStore

NAME_PATTERN = r"^[a-z0-9_-]{1,40}$"


class NewAgent(BaseModel):
    name: str = Field(pattern=NAME_PATTERN)


class IssuedAgent(BaseModel):
    agent_id: str
    name: str
    key_id: str
    api_key: str


class IssuedKey(BaseModel):
    key_id: str
    api_key: str


def build_admin_router(
    registry: AgentRegistry,
    subscriptions: SubscriptionStore | None,
    require_admin: Callable[[Request], Principal],
) -> APIRouter:
    router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

    @router.post("/agents", status_code=201)
    def create_agent(body: NewAgent) -> IssuedAgent:
        key = make_key()
        try:
            agent = registry.create_agent(body.name, key)
        except DuplicateAgentError as exc:
            raise HTTPException(status_code=409, detail="name_taken") from exc
        return IssuedAgent(
            agent_id=agent.id, name=agent.name, key_id=agent.key_id, api_key=key.raw
        )

    @router.get("/agents")
    def list_agents() -> list[AgentSummary]:
        return registry.list_agents()

    @router.get("/subscriptions")
    def list_subscriptions() -> list[AdminSubscription]:
        return subscriptions.list_all() if subscriptions else []

    @router.delete("/subscriptions/{sub_id}", status_code=204)
    def delete_subscription(sub_id: str) -> Response:
        if subscriptions is None or not subscriptions.delete_any(sub_id):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    @router.post("/agents/{agent_id}/keys", status_code=201)
    def issue_key(agent_id: str) -> IssuedKey:
        key = make_key()
        if not any(a.agent_id == agent_id for a in registry.list_agents()):
            raise HTTPException(status_code=404, detail="not_found")
        return IssuedKey(key_id=registry.add_key(agent_id, key), api_key=key.raw)

    @router.delete("/agents/{agent_id}/keys/{key_id}", status_code=204)
    def revoke_key(agent_id: str, key_id: str) -> Response:
        if not registry.revoke_key(agent_id, key_id):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    @router.post("/agents/{agent_id}/disable", status_code=204)
    def disable(agent_id: str) -> Response:
        return _set_status(agent_id, "disabled")

    @router.post("/agents/{agent_id}/enable", status_code=204)
    def enable(agent_id: str) -> Response:
        return _set_status(agent_id, "active")

    def _set_status(agent_id: str, status: str) -> Response:
        if not registry.set_status(agent_id, status):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    return router
