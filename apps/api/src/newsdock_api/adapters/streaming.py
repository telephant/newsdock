"""The shared server-sent-events loop for agent streams and the live feed (ADR-0018).

At-least-once: every event's `id` is the opaque cursor of its article, a reconnect
sends it back as `Last-Event-ID`, and the loop reads strictly after it. The hub only
says "re-query"; the data always comes from the cursor query, filtered in SQL.
Callers supply who is allowed to keep listening (`still_allowed`), re-checked at
least every keep-alive interval, and a `Slot` that is released exactly once.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable

from starlette.concurrency import run_in_threadpool

from newsdock_api.domain.records import NewArticlesPage
from newsdock_api.domain.service import ArticleService, encode_cursor
from newsdock_api.domain.streams import StreamLimiter, WakeHub

BATCH = 200  # articles per query; a full batch is followed by another at once
RETRY_AFTER_SECONDS = "5"
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Slot:
    """One acquired stream slot, released exactly once (generator or background)."""

    def __init__(self, limiter: StreamLimiter, key: str) -> None:
        self._limiter = limiter
        self._key = key
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._limiter.release(self._key)


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


def frame(cursor: str, data: str) -> str:
    return f"id: {cursor}\nevent: article\ndata: {data}\n\n"


async def article_events(
    *,
    service: ArticleService,
    hub: WakeHub,
    query: dict[str, str | None],
    start_cursor: str | None,
    stored_seq: int | None,
    slot: Slot,
    still_allowed: Callable[[], Awaitable[bool]],
    keepalive_seconds: float,
    fallback_poll_seconds: float,
) -> AsyncIterator[str]:
    cursor = start_cursor  # None until the first event (or a Last-Event-ID)
    last_query = 0.0
    last_check = time.monotonic()  # the connect itself just authorized us
    try:
        while True:
            # re-check on a timer, not only on quiet ticks: steady wake-ups
            # (a busy sink) must not starve the revoked-key check
            if time.monotonic() - last_check >= keepalive_seconds:
                last_check = time.monotonic()
                if not await still_allowed():
                    return
            seen = hub.generation()  # noted BEFORE querying: no lost wake-up
            last_query = time.monotonic()
            page = await run_in_threadpool(_page, service, cursor, stored_seq, query)
            for article in page.articles:
                cursor = encode_cursor(article.seq)
                yield frame(cursor, article.model_dump_json())
            if len(page.articles) >= BATCH:
                continue  # more waiting right now
            while True:
                woke = await hub.wait(seen, keepalive_seconds)
                if not woke:
                    yield ": ping\n\n"
                if time.monotonic() - last_check >= keepalive_seconds:
                    last_check = time.monotonic()
                    if not await still_allowed():
                        return
                if woke:
                    break
                if time.monotonic() - last_query >= fallback_poll_seconds:
                    break  # periodic re-query without a notification
    finally:
        slot.release()
