"""Admin routes under /api/admin: manage agents, their keys and subscriptions.

Guarded by `require_admin` (adapters/principal.py): the admin token (CLI) or any
signed-in user. An agent key is a different credential and gets 403; no credential
gets 401. What a caller sees and changes is limited by an `AgentScope` (ADR-0023):
the owner role and the token reach every agent, other users only the ones they
created; a foreign, ownerless (to them) or unknown id is a plain 404. Plaintext
keys appear in a response exactly once, when issued.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from newsdock_api.adapters.agents_repo import DuplicateAgentError
from newsdock_api.domain.accounts import (
    AdminTokenPrincipal,
    Principal,
    UserPrincipal,
    scope_for,
)
from newsdock_api.domain.agents import (
    AgentRegistry,
    AgentScope,
    AgentSummary,
    agent_quota_reached,
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
    *,
    max_agents_per_user: int,
) -> APIRouter:
    router = APIRouter(prefix="/api/admin")

    def caller(request: Request) -> UserPrincipal | AdminTokenPrincipal:
        who = require_admin(request)  # 401/403 for everyone else
        if isinstance(who, UserPrincipal | AdminTokenPrincipal):
            return who
        raise HTTPException(status_code=403, detail="forbidden")

    def scope(who: UserPrincipal | AdminTokenPrincipal = Depends(caller)) -> AgentScope:
        return scope_for(who)

    @router.post("/agents", status_code=201)
    def create_agent(
        body: NewAgent, who: UserPrincipal | AdminTokenPrincipal = Depends(caller)
    ) -> IssuedAgent:
        owner_id = who.user_id if isinstance(who, UserPrincipal) else None
        # The quota binds exactly the callers whose scope is "own": the owner role and
        # the admin token see everything and are exempt (signup-rate-limit D-7). It is
        # checked before the name, so at the cap every name answers too_many_agents.
        # A soft cap: two simultaneous creates may overshoot by the requests in flight.
        if (
            owner_id is not None
            and not scope_for(who).everything
            and agent_quota_reached(registry.count_owned(owner_id), max_agents_per_user)
        ):
            raise HTTPException(status_code=409, detail="too_many_agents")
        key = make_key()
        try:
            agent = registry.create_agent(body.name, key, owner_id)
        except DuplicateAgentError as exc:
            raise HTTPException(status_code=409, detail="name_taken") from exc
        return IssuedAgent(
            agent_id=agent.id, name=agent.name, key_id=agent.key_id, api_key=key.raw
        )

    @router.get("/agents")
    def list_agents(scope: AgentScope = Depends(scope)) -> list[AgentSummary]:
        return registry.list_agents(scope)

    @router.get("/subscriptions")
    def list_subscriptions(
        scope: AgentScope = Depends(scope),
    ) -> list[AdminSubscription]:
        return subscriptions.list_visible(scope) if subscriptions else []

    @router.delete("/subscriptions/{sub_id}", status_code=204)
    def delete_subscription(
        sub_id: str, scope: AgentScope = Depends(scope)
    ) -> Response:
        if subscriptions is None or not subscriptions.delete_visible(sub_id, scope):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    @router.post("/agents/{agent_id}/keys", status_code=201)
    def issue_key(agent_id: str, scope: AgentScope = Depends(scope)) -> IssuedKey:
        key = make_key()
        key_id = registry.add_key(agent_id, key, scope)
        if key_id is None:
            raise HTTPException(status_code=404, detail="not_found")
        return IssuedKey(key_id=key_id, api_key=key.raw)

    @router.delete("/agents/{agent_id}/keys/{key_id}", status_code=204)
    def revoke_key(
        agent_id: str, key_id: str, scope: AgentScope = Depends(scope)
    ) -> Response:
        if not registry.revoke_key(agent_id, key_id, scope):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    @router.post("/agents/{agent_id}/disable", status_code=204)
    def disable(agent_id: str, scope: AgentScope = Depends(scope)) -> Response:
        return _set_status(agent_id, "disabled", scope)

    @router.post("/agents/{agent_id}/enable", status_code=204)
    def enable(agent_id: str, scope: AgentScope = Depends(scope)) -> Response:
        return _set_status(agent_id, "active", scope)

    def _set_status(agent_id: str, status: str, scope: AgentScope) -> Response:
        if not registry.set_status(agent_id, status, scope):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    return router
