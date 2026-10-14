"""Subscription routes for authenticated agents (push-delivery, ADR-0019).

The body of POST is the filter itself. Agents only ever see their own rows: other
agents' ids answer 404. `AuthMiddleware` has already verified the key and stored
the agent on `request.state`; anonymous callers (auth off) own nothing -> 403.
"""

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response

from newsdock_api.domain.agents import Agent
from newsdock_api.domain.subscriptions import (
    InvalidFilter,
    SubscriptionRecord,
    SubscriptionStore,
    parse_filter,
)


def current_agent(request: Request) -> Agent:
    agent = getattr(request.state, "agent", None)
    if not isinstance(agent, Agent):  # the middleware guarantees it; stay safe
        raise HTTPException(status_code=401, detail="unauthorized")
    if agent.id is None:
        raise HTTPException(status_code=403, detail="anonymous_agent")
    return agent


def build_subscriptions_router(
    store: SubscriptionStore, *, max_per_agent: int, max_text_length: int
) -> APIRouter:
    router = APIRouter(prefix="/api/subscriptions")

    @router.post("", status_code=201)
    def create(
        request: Request, body: Any = Body(default_factory=dict)
    ) -> dict[str, Any]:
        agent = current_agent(request)
        try:
            parsed = parse_filter(body, max_text_length)
        except InvalidFilter as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        assert agent.id is not None
        if store.count_own(agent.id) >= max_per_agent:
            raise HTTPException(status_code=409, detail="too_many_subscriptions")
        record = store.create(agent.id, parsed.as_json())
        return _public(record)

    @router.get("")
    def list_own(request: Request) -> list[dict[str, Any]]:
        agent = current_agent(request)
        assert agent.id is not None
        return [_public(r) for r in store.list_own(agent.id)]

    @router.delete("/{sub_id}", status_code=204)
    def delete(sub_id: str, request: Request) -> Response:
        agent = current_agent(request)
        assert agent.id is not None
        if not store.delete_own(agent.id, sub_id):
            raise HTTPException(status_code=404, detail="not_found")
        return Response(status_code=204)

    return router


def _public(record: SubscriptionRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "filter": record.filter,
        "created_at": record.created_at.isoformat(),
    }
