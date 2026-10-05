"""TC-15, TC-16, TC-19, TC-21 (+TC-24 replace) against Postgres + live app (Docker)."""

import asyncio
import json
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from mcp import Client
from mcp.shared.exceptions import MCPError
from newsdock_db.engine import make_engine
from newsdock_db.models import Article
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-api-test"
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def _article(key: str, **kw: Any) -> Article:
    defaults: dict[str, Any] = dict(
        url_hash=key, gkg_record_id="x", slot="20261004081500",
        url=f"https://example.com/{key}", title=f"title {key}", domain="example.com",
        published_at=NOW, themes=["ECON_INFLATION"], persons=[], orgs=[],
    )  # fmt: skip
    defaults.update(kw)
    return Article(**defaults)


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    assert _compose("up", "-d", "--wait", "postgres").returncode == 0
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in (ROOT / ".env.example").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{env.get('POSTGRES_PORT', '5433')}/{env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")

    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE ingest_slot"))
    with Session(engine) as session:
        session.add_all([
            _article("aaa1", published_at=NOW - timedelta(hours=3),
                     themes=["ECON_INFLATION"], domain="alpha.com", title="Fed raises"),
            _article("bbb2", published_at=NOW - timedelta(hours=2),
                     themes=["ENV_CLIMATE"], domain="beta.org", title="Storm season"),
            _article("ccc3", published_at=NOW - timedelta(hours=1),
                     themes=["ECON_STOCKMARKET"], domain="alpha.com",
                     title="Stocks rally 5%"),
        ])  # fmt: skip
        session.commit()
    engine.dispose()

    from newsdock_api.adapters.http import create_app  # after DATABASE_URL is set

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


# TC-15: the client sees exactly the four designed tools
def test_tool_list(base_url: str) -> None:
    async def go() -> list[str]:
        async with Client(f"{base_url}/mcp") as client:
            tools = await client.list_tools()
            return sorted(t.name for t in tools.tools)

    assert _run(go()) == [
        "get_article", "list_new_articles", "search_articles", "submit_analysis",
    ]  # fmt: skip


# TC-16: combined filters return only matching articles, at most limit
def test_search_filters(base_url: str) -> None:
    async def go() -> Any:
        async with Client(f"{base_url}/mcp") as client:
            by_theme = await client.call_tool(
                "search_articles", {"theme": "ECON_INFLATION"}
            )
            by_text = await client.call_tool(
                "search_articles", {"text": "5%", "domain": "alpha.com"}
            )
            windowed = await client.call_tool(
                "search_articles",
                {
                    "time_from": (NOW - timedelta(hours=2, minutes=30)).isoformat(),
                    "time_to": NOW.isoformat(),
                    "limit": 1,
                },
            )
            return (
                by_theme.structured_content,
                by_text.structured_content,
                windowed.structured_content,
            )

    by_theme, by_text, windowed = _run(go())
    assert [a["article_id"] for a in by_theme["articles"]] == ["aaa1"]
    assert [a["article_id"] for a in by_text["articles"]] == ["ccc3"]  # escaped '%'
    assert len(windowed["articles"]) == 1  # limit respected


# TC-19: same cursor, no new data → empty list and the same-or-newer cursor
def test_cursor_semantics(base_url: str) -> None:
    async def go() -> Any:
        async with Client(f"{base_url}/mcp") as client:
            first = await client.call_tool("list_new_articles", {"limit": 200})
            cursor = first.structured_content["next_cursor"]
            again = await client.call_tool(
                "list_new_articles", {"cursor": cursor, "limit": 200}
            )
            return first.structured_content, again.structured_content

    first, again = _run(go())
    assert len(first["articles"]) == 3  # seeded within the first-run window? no:
    # seeded articles have ingested_at = now() (insert time), so all 3 are new
    assert again["articles"] == [] and again["next_cursor"] == first["next_cursor"]


# TC-21 + TC-24: write-back visible via get_article; resubmission replaces
def test_write_back_and_replace(base_url: str) -> None:
    async def go() -> Any:
        async with Client(f"{base_url}/mcp") as client:
            ok = await client.call_tool(
                "submit_analysis",
                {"article_id": "aaa1", "agent_name": "demo",
                 "payload": {"relevant": True, "score": 0.4, "reason": "first"}},
            )  # fmt: skip
            await client.call_tool(
                "submit_analysis",
                {"article_id": "aaa1", "agent_name": "demo",
                 "payload": {"relevant": True, "score": 0.9, "reason": "second"}},
            )  # fmt: skip
            got = await client.call_tool("get_article", {"article_id": "aaa1"})
            try:
                missing = await client.call_tool("get_article", {"article_id": "zzz"})
                missing_is_not_found = bool(missing.is_error) and "not_found" in (
                    json.dumps([c.model_dump() for c in missing.content])
                )
            except MCPError as exc:
                missing_is_not_found = "not_found" in str(exc)
            return ok.structured_content, got.structured_content, missing_is_not_found

    ok, got, missing_is_not_found = _run(go())
    assert ok == {"ok": True}
    analyses = got["analyses"]
    assert len(analyses) == 1  # replaced, not appended
    assert analyses[0]["payload"]["score"] == 0.9
    assert missing_is_not_found


def test_rest_feed_and_health(base_url: str) -> None:
    feed = httpx.get(f"{base_url}/api/articles", params={"theme": "ECON_INFLATION"})
    assert feed.status_code == 200
    items = feed.json()["articles"]
    assert [a["article_id"] for a in items] == ["aaa1"]
    assert items[0]["scores"] == {"demo": 0.9}  # latest score surfaced to the UI
    health = httpx.get(f"{base_url}/api/health").json()
    assert health["db"] is True


def test_rest_keyset_pagination(base_url: str) -> None:
    page1 = httpx.get(f"{base_url}/api/articles", params={"limit": 2}).json()
    assert [a["article_id"] for a in page1["articles"]] == ["ccc3", "bbb2"]
    page2 = httpx.get(
        f"{base_url}/api/articles",
        params={"limit": 2, "before": page1["next_before"]},
    ).json()
    assert [a["article_id"] for a in page2["articles"]] == ["aaa1"]
