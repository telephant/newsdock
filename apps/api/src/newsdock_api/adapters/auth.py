"""Pure-ASGI auth + rate-limit middleware for the agent-only routes (ADR-0016, 0019).

Order: resolve the caller, then rate-limit by verified agent id (or the shared
anonymous bucket), so unauthenticated floods never create limiter entries. The
verified agent travels on `scope["state"]["agent"]` (T-01 spike): MCP tools read
it from the request. Keys are never logged, only their public prefix.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from newsdock_api.domain.agents import ANONYMOUS, Agent, KeyLookup, authenticate
from newsdock_api.domain.ratelimit import ANONYMOUS_BUCKET, FixedWindowLimiter

logger = logging.getLogger(__name__)

PROTECTED_PREFIXES = ("/mcp", "/api/subscriptions")


def _is_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


async def _reply(
    send: Send, status: int, error: str, headers: list[tuple[bytes, bytes]]
) -> None:
    body = b'{"error":"' + error.encode() + b'"}'
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        keys: KeyLookup,
        limiter: FixedWindowLimiter,
        auth_required: bool,
    ) -> None:
        self._app = app
        self._keys = keys
        self._limiter = limiter
        self._auth_required = auth_required

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_protected(scope["path"]):
            await self._app(scope, receive, send)
            return

        header = dict(scope["headers"]).get(b"authorization", b"").decode() or None
        try:
            found = await run_in_threadpool(authenticate, header, self._keys.find_key)
            if found is not None:
                await run_in_threadpool(
                    self._keys.touch_key, found[1], datetime.now(UTC)
                )
        except SQLAlchemyError:
            logger.exception("auth lookup failed")
            await _reply(send, 503, "unavailable", [])
            return

        agent: Agent
        if found is not None:
            agent = found[0]
        elif not self._auth_required:
            agent = ANONYMOUS
        else:
            logger.info("rejected unauthenticated request to %s", scope["path"])
            await _reply(send, 401, "unauthorized", [(b"www-authenticate", b"Bearer")])
            return

        decision = self._limiter.allow(agent.id or ANONYMOUS_BUCKET)
        if not decision.allowed:
            await _reply(
                send,
                429,
                "rate_limited",
                [(b"retry-after", str(decision.retry_after).encode())],
            )
            return

        state = scope.setdefault("state", {})
        state["agent"] = agent
        state["key_id"] = found[1] if found is not None else None
        await self._app(scope, receive, send)
