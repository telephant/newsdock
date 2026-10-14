"""`GET /api/subscriptions/{id}/stream`: Server-Sent Events push (C-16, ADR-0018/0019).

At-least-once: every event's `id` is the opaque cursor of its article, a reconnect
sends it back as `Last-Event-ID`, and the loop reads strictly after it. The hub only
says "re-query"; the data always comes from the cursor query, filtered in SQL.
Connecting never moves the agent's stored cursor (only `ack_cursor` does).
"""

import time
from collections.abc import AsyncIterator
from typing import Annotated, Protocol

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from newsdock_api.adapters.subscriptions_api import current_agent
from newsdock_api.domain.records import NewArticlesPage
from newsdock_api.domain.service import ArticleService, decode_cursor, encode_cursor
from newsdock_api.domain.streams import StreamLimiter, WakeHub
from newsdock_api.domain.subscriptions import SubscriptionRecord, SubscriptionStore

BATCH = 200  # articles per query; a full batch is followed by another at once
RETRY_AFTER_SECONDS = "5"


class AgentState(Protocol):
    """The two reads the stream needs from the agent registry."""

    def get_cursor(self, agent_id: str) -> int | None: ...

    def key_usable(self, key_id: str) -> bool: ...


class _Slot:
    """One acquired stream slot, released exactly once (generator or background)."""

    def __init__(self, limiter: StreamLimiter, agent_id: str) -> None:
        self._limiter = limiter
        self._agent_id = agent_id
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._limiter.release(self._agent_id)


def _page(
    service: ArticleService,
    cursor: str | None,
    stored_seq: int | None,
    query: dict[str, str | None],
) -> NewArticlesPage:
    # the stored position only applies until the first event moves `cursor`
    return service.list_new(
        cursor=cursor,
        limit=BATCH,
        stored_seq=stored_seq if cursor is None else None,
        **query,
    )


def _frame(cursor: str, data: str) -> str:
    return f"id: {cursor}\nevent: article\ndata: {data}\n\n"


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

    async def events(
        sub: SubscriptionRecord,
        key_id: str | None,
        start_cursor: str | None,
        stored_seq: int | None,
        slot: _Slot,
    ) -> AsyncIterator[str]:
        query: dict[str, str | None] = {
            k: sub.filter.get(k) for k in ("theme", "domain", "text")
        }
        cursor = start_cursor  # None until the first event (or a Last-Event-ID)
        last_query = 0.0
        last_check = time.monotonic()  # the connect itself just authorized us
        try:
            while True:
                # re-check on a timer, not only on quiet ticks: steady wake-ups
                # (a busy sink) must not starve the revoked-key check
                if time.monotonic() - last_check >= keepalive_seconds:
                    last_check = time.monotonic()
                    if not await _still_allowed(sub, key_id):
                        return
                seen = hub.generation()  # noted BEFORE querying: no lost wake-up
                last_query = time.monotonic()
                page = await run_in_threadpool(
                    _page, service, cursor, stored_seq, query
                )
                for article in page.articles:
                    cursor = encode_cursor(article.seq)
                    yield _frame(cursor, article.model_dump_json())
                if len(page.articles) >= BATCH:
                    continue  # more waiting right now
                while True:
                    woke = await hub.wait(seen, keepalive_seconds)
                    if not woke:
                        yield ": ping\n\n"
                    if time.monotonic() - last_check >= keepalive_seconds:
                        last_check = time.monotonic()
                        if not await _still_allowed(sub, key_id):
                            return
                    if woke:
                        break
                    if time.monotonic() - last_query >= fallback_poll_seconds:
                        break  # periodic re-query without a notification
        finally:
            slot.release()

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
        slot = _Slot(limiter, agent.id)
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
        return StreamingResponse(
            events(sub, key_id, last_event_id or None, stored, slot),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(slot.release),  # if the generator never ran
        )

    return router
