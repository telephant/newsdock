"""One FastAPI process: MCP (streamable HTTP, /mcp) + REST (/api/*) (ADR-0003).

Spike-verified pattern (spike.md §1): mount `mcp.streamable_http_app()` and run
`mcp.session_manager.run()` inside the host app's lifespan.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_api.adapters.kafka_health import kafka_reachable
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.config import Settings
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
    get_article,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    repo = SqlArticleRepo(make_engine(DbSettings()))
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
        cursor: str | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """List articles newer than the cursor; no cursor = the last hour."""
        page: NewArticlesPage = service.list_new(cursor=cursor, limit=limit)
        return page.model_dump(mode="json")

    @mcp.tool()
    def submit_analysis(
        article_id: str, agent_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Store an agent's analysis for an article (payload: any JSON object)."""
        try:
            service.submit_analysis(article_id, agent_name, payload)
        except NotFoundError as exc:
            raise ToolError(f"not_found: {exc}") from exc
        except PayloadTooLargeError as exc:
            raise ToolError(f"payload_too_large: {exc}") from exc
        return {"ok": True}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="newsdock API", lifespan=lifespan)
    app.add_middleware(  # the web UI calls /api/* from the browser (TC-25)
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )

    @app.get("/api/articles")
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

    @app.get("/api/articles/{article_id}")
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
    return app
