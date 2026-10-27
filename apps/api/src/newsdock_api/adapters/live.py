"""`GET /api/live`: the web UI's live feed (C-14), server-sent events for a user.

Same engine as the agent streams (`adapters/streaming.py`, ADR-0018): `NOTIFY` only
wakes it, the data comes from the cursor query. Differences: the caller is a session
(any role), there is no stored cursor (it starts at the newest article, so no
backlog; the feed page loads history over REST) and each keep-alive tick re-checks
the session, so logout, expiry or deleting the account ends the stream.
An optional ad-hoc filter (`theme`, `domain`, `text`) uses the subscription rules.
In dev mode (`auth_required` false) the feed is open and not session-bound.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from newsdock_api.adapters.streaming import (
    RETRY_AFTER_SECONDS,
    STREAM_HEADERS,
    Slot,
    article_events,
)
from newsdock_api.domain.accounts import UserPrincipal
from newsdock_api.domain.service import ArticleService, decode_cursor
from newsdock_api.domain.streams import StreamLimiter, WakeHub
from newsdock_api.domain.subscriptions import InvalidFilter, parse_filter

ANONYMOUS_KEY = "anonymous"  # dev mode: one shared cap for everybody


def build_live_router(
    *,
    service: ArticleService,
    hub: WakeHub,
    limiter: StreamLimiter,
    require_live: Callable[[Request], UserPrincipal | None],
    session_alive: Callable[[str], bool],
    cookie_name: str,
    keepalive_seconds: float,
    fallback_poll_seconds: float,
    max_text_length: int,
) -> APIRouter:
    router = APIRouter(prefix="/api/live")

    @router.get("")
    async def live(
        request: Request,
        user: Annotated[UserPrincipal | None, Depends(require_live)],
        theme: Annotated[str | None, Query()] = None,
        domain: Annotated[str | None, Query()] = None,
        text: Annotated[str | None, Query()] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        given = {
            k: v
            for k, v in (("theme", theme), ("domain", domain), ("text", text))
            if v is not None
        }
        try:
            query = parse_filter(given, max_text_length).as_query()
        except InvalidFilter as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if last_event_id:
            try:
                decode_cursor(last_event_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid_last_event_id"
                ) from exc
        key = f"user:{user.user_id}" if user else ANONYMOUS_KEY
        if not limiter.try_acquire(key):
            raise HTTPException(
                status_code=429,
                detail="too_many_streams",
                headers={"Retry-After": RETRY_AFTER_SECONDS},
            )
        slot = Slot(limiter, key)
        try:
            # read the end of the table now, before streaming: anything stored after
            # this point is delivered, nothing before it is
            start = last_event_id or await run_in_threadpool(service.latest_cursor)
        except BaseException:
            slot.release()
            raise
        token = request.cookies.get(cookie_name)

        async def still_allowed() -> bool:
            if user is None:
                return True
            return bool(token) and await run_in_threadpool(session_alive, token or "")

        return StreamingResponse(
            article_events(
                service=service,
                hub=hub,
                query=query,
                start_cursor=start,
                stored_seq=None,
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
