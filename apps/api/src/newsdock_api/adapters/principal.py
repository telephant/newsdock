"""Who is calling? One resolver for the three credentials, plus route guards (C-12).

Resolution (design-detail §2): if an `Authorization` header is present it alone
decides (agent key, else the admin token, else anonymous: no fallback to a
cookie); otherwise the session cookie decides. The guards are FastAPI
dependencies, i.e. they run *inside* the CORS middleware, so a 401 or 403 keeps its
CORS headers and the credentialed web UI can read it. Agent paths (/mcp,
/api/subscriptions) keep their own enforcement in `AuthMiddleware` (ADR-0016/0019).
"""

import hmac
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from newsdock_api.domain.accounts import (
    AdminTokenPrincipal,
    AgentPrincipal,
    Principal,
    SessionStore,
    UserPrincipal,
    can,
    hash_token,
    session_valid,
    should_touch,
)
from newsdock_api.domain.agents import KeyLookup, authenticate

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PrincipalResolver:
    def __init__(
        self,
        *,
        sessions: SessionStore,
        keys: KeyLookup,
        admin_token: str | None,
        idle: timedelta,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._sessions = sessions
        self._keys = keys
        self._admin_token = admin_token
        self._idle = idle
        self._clock = clock

    def resolve(
        self, authorization: str | None, session_cookie: str | None
    ) -> Principal:
        if authorization is not None:
            return self._from_authorization(authorization)
        if session_cookie:
            return self._from_cookie(session_cookie)
        return None

    def session_alive(self, token: str) -> bool:
        """Is this cookie still a live session? (open streams re-check it)"""
        return isinstance(self._from_cookie(token), UserPrincipal)

    def _from_authorization(self, header: str) -> Principal:
        found = authenticate(header, self._keys.find_key)
        if found is not None:
            agent, key_id = found
            self._keys.touch_key(key_id, self._clock())
            return AgentPrincipal(agent=agent, key_id=key_id)
        scheme, _, presented = header.partition(" ")
        presented = presented.strip()
        if (
            self._admin_token
            and scheme.lower() == "bearer"
            and presented
            and hmac.compare_digest(presented.encode(), self._admin_token.encode())
        ):
            return AdminTokenPrincipal()
        return None

    def _from_cookie(self, token: str) -> Principal:
        stored_hash = hash_token(token)
        info = self._sessions.find_session(stored_hash)
        if info is None:
            return None
        now = self._clock()
        if not session_valid(
            now,
            last_seen_at=info.last_seen_at,
            expires_at=info.expires_at,
            idle=self._idle,
        ):
            self._sessions.delete_session(stored_hash)
            return None
        if should_touch(now, info.last_seen_at):
            self._sessions.touch_session(stored_hash, now)
        return UserPrincipal(user_id=info.user_id, email=info.email, role=info.role)


class Guards(NamedTuple):
    principal: Callable[[Request], Principal]
    read: Callable[[Request], None]  # a user or an agent (open when auth is off)
    user: Callable[[Request], UserPrincipal]  # a logged-in human, always
    write: Callable[[Request], None]  # app-wide: Origin allowlist + JSON bodies
    admin: Callable[[Request], Principal]  # admin token, or admin/owner session
    manage_users: Callable[[Request], UserPrincipal]  # owner session only
    admin_token_only: Callable[[Request], None]  # the CLI token, nothing else
    live: Callable[
        [Request], UserPrincipal | None
    ]  # live feed: a user, or anyone in dev
    session_alive: Callable[[str], bool]


def build_guards(
    resolver: PrincipalResolver,
    *,
    auth_required: bool,
    cookie_name: str,
    allowed_origins: list[str],
    admin_token_configured: bool,
) -> Guards:
    def principal(request: Request) -> Principal:
        state = request.state
        if hasattr(state, "principal"):
            cached: Principal = state.principal
            return cached
        try:
            resolved = resolver.resolve(
                request.headers.get("authorization"), request.cookies.get(cookie_name)
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="unavailable") from exc
        state.principal = resolved
        return resolved

    def read(request: Request) -> None:
        if not auth_required:
            return
        if isinstance(principal(request), UserPrincipal | AgentPrincipal):
            return
        raise HTTPException(status_code=401, detail="unauthorized")

    def user(request: Request) -> UserPrincipal:
        who = principal(request)
        if isinstance(who, UserPrincipal):
            return who
        raise HTTPException(status_code=401, detail="unauthorized")

    def write(request: Request) -> None:
        if request.method not in WRITE_METHODS:
            return
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            raise HTTPException(status_code=403, detail="bad_origin")
        length = request.headers.get("content-length")
        has_body = (length not in (None, "0")) or (
            "chunked" in request.headers.get("transfer-encoding", "").lower()
        )
        media = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if has_body and media != "application/json":
            raise HTTPException(status_code=415, detail="unsupported_media_type")

    def forbidden_or_unauthorized(who: Principal) -> HTTPException:
        # a known caller without the right: 403; nobody (or the wrong kind): 401
        if isinstance(who, UserPrincipal | AgentPrincipal):
            return HTTPException(status_code=403, detail="forbidden")
        return HTTPException(status_code=401, detail="unauthorized")

    def admin(request: Request) -> Principal:
        who = principal(request)
        if isinstance(who, AdminTokenPrincipal):
            return who
        if isinstance(who, UserPrincipal) and can(who.role, "manage_agents"):
            return who
        raise forbidden_or_unauthorized(who)

    def manage_users(request: Request) -> UserPrincipal:
        who = principal(request)
        if isinstance(who, UserPrincipal) and can(who.role, "manage_users"):
            return who
        raise forbidden_or_unauthorized(who)

    def live(request: Request) -> UserPrincipal | None:
        # dev mode (auth off) opens the feed like the reads; otherwise a user, any role
        if not auth_required:
            return None
        who = principal(request)
        if isinstance(who, UserPrincipal):
            return who
        raise forbidden_or_unauthorized(who)  # nobody: 401; an agent key: 403

    def admin_token_only(request: Request) -> None:
        # no token configured: the route does not exist; sessions never qualify, so
        # an admin cannot take over the owner account
        if not admin_token_configured:
            raise HTTPException(status_code=404)
        who = principal(request)
        if isinstance(who, AdminTokenPrincipal):
            return
        raise forbidden_or_unauthorized(who)

    return Guards(
        principal=principal,
        read=read,
        user=user,
        write=write,
        admin=admin,
        manage_users=manage_users,
        admin_token_only=admin_token_only,
        live=live,
        session_alive=resolver.session_alive,
    )
