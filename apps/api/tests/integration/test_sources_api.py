"""M2a TC-6, TC-7, TC-8: sources/source_count via MCP + REST (Docker)."""

import asyncio
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
from newsdock_db.engine import make_engine
from newsdock_db.models import Article, ArticleSource
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-apisrc-test"
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
STORY = "canon1"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def _article(key: str, **kw: Any) -> Article:
    defaults: dict[str, Any] = dict(
        url_hash=key, gkg_record_id="x", slot="20261005120000",
        url=f"https://example.com/{key}", title=f"title {key}",
        domain="example.com", published_at=NOW, themes=["ECON_TEST"],
        persons=[], orgs=[], story_key=f"story {key}",
    )  # fmt: skip
    defaults.update(kw)
    return Article(**defaults)


def _source(key: str, canonical: str, hours: float = 0.0) -> ArticleSource:
    return ArticleSource(
        url_hash=key, article_id=canonical, url=f"https://s.example/{key}",
        domain=f"{key}.example", slot="20261005120000", gkg_record_id="x",
        published_at=NOW + timedelta(hours=hours),
    )  # fmt: skip


@pytest.fixture(scope="module")
def stack_urls() -> Iterator[tuple[str, str]]:
    """Yields (api base url, database url)."""
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
    with Session(engine) as session:
        session.add(_article(STORY))  # grouped story: 3 sources
        session.add(_article("plain2", story_key="story plain2"))
        session.add(_article("legacy3", story_key=None))  # pre-feature row
        session.commit()
        session.add_all([
            _source(STORY, STORY),
            _source("copy-a", STORY, hours=1),
            _source("copy-b", STORY, hours=2),
            _source("plain2", "plain2"),
        ])  # fmt: skip
        session.commit()
    engine.dispose()

    from newsdock_api.adapters.http import create_app

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
    yield f"http://127.0.0.1:{port}", url
    server.should_exit = True
    thread.join(timeout=10)
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


# TC-6: the detail exposes all sources and the count, on both surfaces
def test_detail_lists_sources(stack_urls: tuple[str, str]) -> None:
    base_url, _ = stack_urls

    async def go() -> Any:
        async with Client(f"{base_url}/mcp") as client:
            got = await client.call_tool("get_article", {"article_id": STORY})
            return got.structured_content

    mcp_detail = _run(go())
    rest_detail = httpx.get(f"{base_url}/api/articles/{STORY}").json()
    for detail in (mcp_detail, rest_detail):
        assert detail["source_count"] == 3
        domains = [s["domain"] for s in detail["sources"]]
        assert domains == [f"{STORY}.example", "copy-a.example", "copy-b.example"]


# TC-7: feed/search return each story once with its count; NULL-key row reads 1
def test_feed_counts_and_null_key_fallback(stack_urls: tuple[str, str]) -> None:
    base_url, _ = stack_urls
    feed = httpx.get(f"{base_url}/api/articles").json()["articles"]
    counts = {a["article_id"]: a["source_count"] for a in feed}
    assert counts == {STORY: 3, "plain2": 1, "legacy3": 1}
    assert [a["article_id"] for a in feed].count(STORY) == 1


# TC-8: a late copy does not re-emit the story through the cursor
def test_late_copy_does_not_reemit(stack_urls: tuple[str, str]) -> None:
    base_url, db_url = stack_urls

    async def go() -> Any:
        async with Client(f"{base_url}/mcp") as client:
            first = await client.call_tool("list_new_articles", {"limit": 200})
            cursor = first.structured_content["next_cursor"]
            # a new copy arrives for the already-listed story (source only)
            engine = make_engine(db_url)
            with Session(engine) as session:
                session.add(_source("late-copy", STORY, hours=3))
                session.commit()
            engine.dispose()
            again = await client.call_tool(
                "list_new_articles", {"cursor": cursor, "limit": 200}
            )
            return first.structured_content, again.structured_content

    first, again = _run(go())
    assert len(first["articles"]) == 3
    assert again["articles"] == [] and again["next_cursor"] == first["next_cursor"]
