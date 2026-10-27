"""`GET /api/subscriptions/{id}/stream`: Server-Sent Events push (C-16, ADR-0018/0019).

The event loop itself is shared with the live feed (`adapters/streaming.py`); this
module only decides who may listen: the owning agent, re-checked every keep-alive
(key still usable, subscription still there). Connecting never moves the agent's
stored cursor (only `ack_cursor` does).
"""

from typing import Annotated, Protocol

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from newsdock_api.adapters.streaming import (
    RETRY_AFTER_SECONDS,
    STREAM_HEADERS,
    Slot,
    article_events,
)
from newsdock_api.adapters.subscriptions_api import current_agent
from newsdock_api.domain.service import ArticleService, decode_cursor
from newsdock_api.domain.streams import StreamLimiter, WakeHub
from newsdock_api.domain.subscriptions import SubscriptionRecord, SubscriptionStore


class AgentState(Protocol):
    """The two reads the stream needs from the agent registry."""

    def get_cursor(self, agent_id: str) -> int | None: ...

    def key_usable(self, key_id: str) -> bool: ...


def build_stream_router(
    *,
    subscriptions: SubscriptionStore,
    service: ArticleService,
    agents: AgentState,
    hub: WakeHub,
    limiter: StreamLimiter,
    keepalive_seconds: float,
    fallback_poll_seconds: float,
) -> APIRouter:
    router = APIRouter(prefix="/api/subscriptions")

    async def _still_allowed(sub: SubscriptionRecord, key_id: str | None) -> bool:
        if key_id is not None and not await run_in_threadpool(
            agents.key_usable, key_id
        ):
            return False
        return await run_in_threadpool(subscriptions.exists, sub.id)

    @router.get("/{sub_id}/stream")
    async def stream(
        sub_id: str,
        request: Request,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        agent = current_agent(request)
        assert agent.id is not None
        sub = await run_in_threadpool(subscriptions.get_own, agent.id, sub_id)
        if sub is None:
            raise HTTPException(status_code=404, detail="not_found")
        if last_event_id:
            try:
                decode_cursor(last_event_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid_last_event_id"
                ) from exc
        if not limiter.try_acquire(agent.id):
            raise HTTPException(
                status_code=429,
                detail="too_many_streams",
                headers={"Retry-After": RETRY_AFTER_SECONDS},
            )
        slot = Slot(limiter, agent.id)
        try:
            stored = (
                None
                if last_event_id
                else await run_in_threadpool(agents.get_cursor, agent.id)
            )
        except BaseException:
            slot.release()
            raise
        key_id = getattr(request.state, "key_id", None)
        query: dict[str, str | None] = {
            k: sub.filter.get(k) for k in ("theme", "domain", "text")
        }

        async def still_allowed() -> bool:
            return await _still_allowed(sub, key_id)

        return StreamingResponse(
            article_events(
                service=service,
                hub=hub,
                query=query,
                start_cursor=last_event_id or None,
                stored_seq=stored,
                slot=slot,
                still_allowed=still_allowed,
                keepalive_seconds=keepalive_seconds,
                fallback_poll_seconds=fallback_poll_seconds,
            ),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
            background=BackgroundTask(slot.release),  # if the generator never ran
        )

    return router
