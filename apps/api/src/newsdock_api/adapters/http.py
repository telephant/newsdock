"""One FastAPI process: MCP (streamable HTTP, /mcp) + REST (/api/*) (ADR-0003).

Spike-verified pattern (spike.md §1): mount `mcp.streamable_http_app()` and run
`mcp.session_manager.run()` inside the host app's lifespan.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_api.adapters.accounts_api import (
    build_accounts_router,
    build_users_router,
)
from newsdock_api.adapters.admin import build_admin_router
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.auth import AuthMiddleware
from newsdock_api.adapters.kafka_health import kafka_reachable
from newsdock_api.adapters.listener import NotifyListener, listen_dsn
from newsdock_api.adapters.passwords import Argon2Hasher, make_dummy_hash
from newsdock_api.adapters.principal import PrincipalResolver, build_guards
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.sse import build_stream_router
from newsdock_api.adapters.subscriptions_api import build_subscriptions_router
from newsdock_api.adapters.subscriptions_repo import SqlSubscriptionsRepo
from newsdock_api.adapters.users_repo import SqlUsersRepo
from newsdock_api.config import Settings
from newsdock_api.domain.accounts import PasswordHasher, UsersStore
from newsdock_api.domain.agents import (
    ANONYMOUS,
    Agent,
    AgentRegistry,
    KeyLookup,
)
from newsdock_api.domain.loginlimit import LoginLimiter
from newsdock_api.domain.ratelimit import FixedWindowLimiter
from newsdock_api.domain.records import (
    ArticleDetail,
    FeedPage,
    HealthStatus,
    NewArticlesPage,
)
from newsdock_api.domain.service import (
    ArticleService,
    NotFoundError,
    PayloadTooLargeError,
    decode_cursor,
    encode_cursor,
    get_article,
)
from newsdock_api.domain.streams import StreamLimiter, WakeHub
from newsdock_api.domain.subscriptions import SubscriptionStore


def create_app(
    settings: Settings | None = None,
    agents_repo: AgentRegistry | None = None,
    subscriptions_repo: SubscriptionStore | None = None,
    key_lookup: KeyLookup | None = None,
    users_repo: UsersStore | None = None,
    hasher: PasswordHasher | None = None,
    login_limiter: LoginLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(DbSettings())
    repo = SqlArticleRepo(engine)
    sql_agents = SqlAgentsRepo(engine)
    registry: AgentRegistry = agents_repo or sql_agents
    keys: KeyLookup = key_lookup or sql_agents
    accounts: UsersStore = users_repo or SqlUsersRepo(engine)
    password_hasher: PasswordHasher = hasher or Argon2Hasher()
    subscriptions: SubscriptionStore = subscriptions_repo or SqlSubscriptionsRepo(
        engine
    )

    def current_agent(ctx: Context) -> Agent:
        """The caller verified by AuthMiddleware (state set per request)."""
        request = ctx.request_context.request
        agent = getattr(getattr(request, "state", None), "agent", None)
        if isinstance(agent, Agent):
            return agent
        if settings.auth_required:  # defence in depth: never fall back to anonymous
            raise ToolError("unauthorized: no verified agent on the request")
        return ANONYMOUS

    service = ArticleService(repo, limits=settings.limits())

    mcp = MCPServer("newsdock")

    @mcp.tool()
    def search_articles(
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        theme: str | None = None,
        domain: str | None = None,
        text: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Search stored articles by time range, theme, domain and title text."""
        articles = service.search(
            time_from=time_from, time_to=time_to, theme=theme,
            domain=domain, text=text, limit=limit,
        )  # fmt: skip
        return {"articles": [a.model_dump(mode="json") for a in articles]}

    @mcp.tool(name="get_article")
    def get_article_tool(article_id: str) -> dict[str, Any]:
        """Fetch one article with all its analyses. article_id = url_hash."""
        try:
            return get_article(repo, article_id).model_dump(mode="json")
        except NotFoundError as exc:
            raise ToolError(f"not_found: {exc}") from exc

    @mcp.tool()
    def list_new_articles(
        ctx: Context, cursor: str | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """List articles newer than the cursor.

        Without a cursor an authenticated agent resumes from the position it last
        acknowledged with ack_cursor; a new agent gets the last hour.
        """
        agent = current_agent(ctx)
        stored = None
        if cursor is None and agent.id is not None:
            stored = sql_agents.get_cursor(agent.id)
        try:
            page: NewArticlesPage = service.list_new(
                cursor=cursor, limit=limit, stored_seq=stored
            )
        except ValueError as exc:
            raise ToolError(f"invalid_cursor: {exc}") from exc
        return page.model_dump(mode="json")

    @mcp.tool()
    def ack_cursor(cursor: str, ctx: Context) -> dict[str, Any]:
        """Acknowledge that every article up to `cursor` is processed.

        Call it with the next_cursor of a batch after you finished that batch; the
        next list_new_articles without a cursor then starts there. Moves forward
        only; safe to repeat.
        """
        agent = current_agent(ctx)
        if agent.id is None:
            raise ToolError("anonymous_agent: register an agent to keep a cursor")
        try:
            seq = decode_cursor(cursor)
        except ValueError as exc:
            raise ToolError(f"invalid_cursor: {exc}") from exc
        return {"cursor": encode_cursor(sql_agents.advance_cursor(agent.id, seq))}

    @mcp.tool()
    def submit_analysis(
        article_id: str, agent_name: str, payload: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        """Store an analysis for an article (payload: any JSON object).

        Authenticated agents are recorded under their registered name;
        `agent_name` is only honoured for anonymous callers (auth off).
        """
        agent = current_agent(ctx)
        name = agent_name if agent.is_anonymous else agent.name
        try:
            service.submit_analysis(article_id, name, payload)
        except NotFoundError as exc:
            raise ToolError(f"not_found: {exc}") from exc
        except PayloadTooLargeError as exc:
            raise ToolError(f"payload_too_large: {exc}") from exc
        return {"ok": True}

    hub = WakeHub()  # shared with the SSE streams (ADR-0018)
    listener = NotifyListener(listen_dsn(DbSettings().database_url), hub)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        listener_task = asyncio.create_task(listener.run())
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)

    admin_token = settings.admin_token
    guards = build_guards(
        PrincipalResolver(
            sessions=accounts,
            keys=keys,
            admin_token=admin_token.get_secret_value() if admin_token else None,
            idle=settings.session_idle,
        ),
        auth_required=settings.auth_required,
        cookie_name=settings.auth_cookie_name,
        allowed_origins=settings.cors_origins_list,
    )
    app = FastAPI(
        title="newsdock API",
        lifespan=lifespan,
        dependencies=[Depends(guards.write)],  # Origin allowlist + JSON bodies
    )
    app.state.wake_hub = hub
    app.add_middleware(  # the web UI calls /api/* from the browser (TC-25)
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )

    app.include_router(build_admin_router(registry, subscriptions, guards.admin))
    app.include_router(build_users_router(accounts, guards.manage_users))
    app.include_router(
        build_stream_router(
            subscriptions=subscriptions,
            service=service,
            agents=sql_agents,
            hub=hub,
            limiter=StreamLimiter(settings.sse_max_streams_per_agent),
            keepalive_seconds=settings.sse_keepalive_seconds,
            fallback_poll_seconds=settings.sse_fallback_poll_seconds,
        )
    )
    app.include_router(
        build_accounts_router(
            accounts,
            password_hasher,
            login_limiter
            or LoginLimiter(
                settings.auth_login_max_failures, settings.login_window_seconds
            ),
            require_user=guards.user,
            dummy_hash=make_dummy_hash(password_hasher),
            signup_open=settings.auth_signup_open,
            min_password_length=settings.auth_min_pw_length,
            cookie_name=settings.auth_cookie_name,
            cookie_secure=settings.auth_cookie_secure,
            session_idle=settings.session_idle,
            session_absolute=settings.session_absolute,
        )
    )
    app.include_router(
        build_subscriptions_router(
            subscriptions,
            max_per_agent=settings.subscriptions_max_per_agent,
            max_text_length=settings.subscription_text_max_length,
        )
    )

    @app.get("/api/articles", dependencies=[Depends(guards.read)])
    def rest_articles(
        theme: str | None = None,
        domain: str | None = None,
        text: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int | None = None,
        before: str | None = None,
    ) -> FeedPage:
        before_key: tuple[datetime, str] | None = None
        if before:
            raw_ts, _, raw_hash = before.partition(",")
            try:
                before_key = (datetime.fromisoformat(raw_ts), raw_hash)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid_before") from exc
        articles = service.search(
            time_from=time_from, time_to=time_to, theme=theme,
            domain=domain, text=text, limit=limit, before=before_key,
        )  # fmt: skip
        next_before = (
            f"{articles[-1].published_at.isoformat()},{articles[-1].article_id}"
            if articles
            else None
        )
        return FeedPage(articles=articles, next_before=next_before)

    @app.get("/api/articles/{article_id}", dependencies=[Depends(guards.read)])
    def rest_article(article_id: str) -> ArticleDetail:
        try:
            return get_article(repo, article_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="not_found") from exc

    @app.get("/api/health")
    def rest_health() -> HealthStatus:
        health = repo.health()
        return HealthStatus(
            db=bool(health["db"]),
            last_published_slot=health["last_published_slot"],
            kafka=kafka_reachable(
                settings.kafka_bootstrap_servers,
                settings.kafka_probe_timeout_seconds,
            ),
        )

    app.mount(
        "/",
        mcp.streamable_http_app(
            # keep DNS-rebinding protection on, but accept the compose-internal
            # hostname the agent uses (421 Misdirected Request otherwise)
            transport_security=TransportSecuritySettings(
                allowed_hosts=settings.allowed_hosts_list
            )
        ),
    )
    app.add_middleware(
        AuthMiddleware,
        keys=keys,
        limiter=FixedWindowLimiter(settings.rate_limit_per_minute),
        auth_required=settings.auth_required,
    )
    return app
