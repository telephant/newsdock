"""TC-4…TC-7, TC-11 (behaviour), TC-13, TC-17: MCP auth over a live app (Docker)."""

import asyncio
import logging
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import httpx2
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from newsdock_db.models import Article
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-auth-test"
NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
ADMIN_TOKEN = "admin-token-for-auth-tests"
LIMIT = 6  # requests per minute in the limited app


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@contextmanager
def _serve(settings: Settings) -> Iterator[str]:
    from newsdock_api.adapters.http import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings), host="127.0.0.1", port=port, log_level="warning"
        )
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
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
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
    eng = make_engine(url)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE agents CASCADE"))
    with Session(eng) as session:
        session.add(
            Article(
                url_hash="art1",
                gkg_record_id="x",
                slot="20261014120000",
                url="https://example.com/art1",
                title="title art1",
                domain="example.com",
                published_at=NOW,
                themes=["ECON_TEST"],
                persons=[],
                orgs=[],
                story_key="story art1",
            )  # fmt: skip
        )
        session.commit()
    yield eng
    eng.dispose()
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


@pytest.fixture(scope="module")
def keys(engine: Engine) -> dict[str, str]:
    repo = SqlAgentsRepo(engine)
    out: dict[str, str] = {}
    for name in ("alpha", "beta", "gamma", "delta"):
        key = make_key()
        repo.create_agent(name, key)
        out[name] = key.raw
    return out


@pytest.fixture(scope="module")
def secured(engine: Engine, keys: dict[str, str]) -> Iterator[str]:
    settings = Settings(
        auth_required=True, rate_limit_per_minute=LIMIT, admin_token=ADMIN_TOKEN
    )
    with _serve(settings) as url:
        yield url


@pytest.fixture(scope="module")
def open_limit(engine: Engine, keys: dict[str, str]) -> Iterator[str]:
    """Auth on, no rate limit: for tests that open several MCP sessions."""
    with _serve(Settings(auth_required=True, rate_limit_per_minute=0)) as url:
        yield url


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def _client(base: str, key: str | None) -> Client:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    http = httpx2.AsyncClient(headers=headers)
    return Client(streamable_http_client(f"{base}/mcp", http_client=http))


def _call(base: str, key: str | None, tool: str, args: dict[str, Any]) -> Any:
    async def go() -> Any:
        async with _client(base, key) as client:
            return (await client.call_tool(tool, args)).structured_content

    return _run(go())


def _raw_post(base: str, key: str | None) -> httpx.Response:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if key is not None:
        headers["Authorization"] = key
    return httpx.post(f"{base}/mcp", headers=headers, json={}, timeout=10)


# TC-4: no key, a malformed header, an unknown key → 401 before any tool runs
def test_missing_malformed_or_unknown_key_is_401(secured: str) -> None:
    unknown = make_key().raw
    for header in (None, "Bearer", "Basic abc", "Bearer junk", f"Bearer {unknown}"):
        response = _raw_post(secured, header)
        assert response.status_code == 401, header
        assert response.headers["www-authenticate"] == "Bearer"
    with pytest.raises(BaseException):  # noqa: B017, PT011 — client sees the 401
        _call(secured, None, "list_new_articles", {})


# TC-5: a valid key works
def test_valid_key_can_search(secured: str, keys: dict[str, str]) -> None:
    got = _call(secured, keys["delta"], "search_articles", {})
    assert [a["article_id"] for a in got["articles"]] == ["art1"]


# TC-6: revoked key and disabled agent are rejected, re-enabling restores
def test_revoked_and_disabled(secured: str, engine: Engine) -> None:
    repo = SqlAgentsRepo(engine)
    key = make_key()
    agent = repo.create_agent("zeta", key)
    header = f"Bearer {key.raw}"
    assert _raw_post(secured, header).status_code != 401

    repo.set_status(agent.id, "disabled")
    assert _raw_post(secured, header).status_code == 401
    repo.set_status(agent.id, "active")
    assert _raw_post(secured, header).status_code != 401

    repo.revoke_key(agent.id, agent.key_id)
    assert _raw_post(secured, header).status_code == 401
    repo.set_status(agent.id, "active")
    assert _raw_post(secured, header).status_code == 401  # revoked stays revoked


# TC-7: the authenticated name wins over the caller-supplied one
def test_analysis_carries_the_authenticated_identity(
    secured: str, keys: dict[str, str], engine: Engine
) -> None:
    _call(
        secured, keys["alpha"], "submit_analysis",
        {"article_id": "art1", "agent_name": "beta", "payload": {"score": 0.5}},
    )  # fmt: skip
    with engine.connect() as conn:
        names = conn.execute(text("SELECT agent_name FROM analyses")).scalars().all()
    assert names == ["alpha"]


# TC-13: alpha is limited after N requests, beta is not affected
def test_rate_limit_isolates_agents(secured: str, keys: dict[str, str]) -> None:
    # use a fresh minute so earlier tests' requests do not count
    time.sleep(61 - time.time() % 60)
    statuses = [_raw_post(secured, f"Bearer {keys['gamma']}") for _ in range(LIMIT + 1)]
    assert all(r.status_code != 429 for r in statuses[:LIMIT])
    assert statuses[LIMIT].status_code == 429
    assert 1 <= int(statuses[LIMIT].headers["retry-after"]) <= 60
    assert _raw_post(secured, f"Bearer {keys['beta']}").status_code != 429


# TC-11 (behaviour): auth off → anonymous; no ack, caller name kept
def test_auth_off_is_anonymous(engine: Engine) -> None:
    settings = Settings(auth_required=False, rate_limit_per_minute=0)
    with _serve(settings) as base:
        got = _call(base, None, "search_articles", {})
        assert got["articles"]
        _call(
            base, None, "submit_analysis",
            {"article_id": "art1", "agent_name": "legacy", "payload": {"score": 1}},
        )  # fmt: skip
    with engine.connect() as conn:
        names = conn.execute(text("SELECT agent_name FROM analyses")).scalars().all()
    assert "legacy" in names


# TC-17: neither the key secret nor the admin token reaches the logs
def test_secrets_are_not_logged(
    secured: str, keys: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    created = httpx.post(
        f"{secured}/api/admin/agents",
        json={"name": "logcheck"},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    ).json()
    secret = created["api_key"].split("_")[2]
    _raw_post(secured, f"Bearer {created['api_key']}")
    _raw_post(secured, f"Bearer {keys['alpha']}x")
    logged = caplog.text
    assert secret not in logged and ADMIN_TOKEN not in logged


# --- T-06: server-side cursor (AC-8, AC-9) ---------------------------------


def _new_agent(engine: Engine, name: str) -> str:
    key = make_key()
    SqlAgentsRepo(engine).create_agent(name, key)
    return key.raw


def _add_article(engine: Engine, key: str) -> None:
    with Session(engine) as session:
        session.add(
            Article(
                url_hash=key,
                gkg_record_id="x",
                slot="20261014120000",
                url=f"https://example.com/{key}",
                title=f"title {key}",
                domain="example.com",
                published_at=NOW,
                themes=["ECON_TEST"],
                persons=[],
                orgs=[],
                story_key=f"story {key}",
            )  # fmt: skip
        )
        session.commit()


def _ids(page: dict[str, Any]) -> list[str]:
    return [a["article_id"] for a in page["articles"]]


# TC-9: acked position survives a new session; without an ack the batch repeats
def test_server_cursor_resumes_after_ack(open_limit: str, engine: Engine) -> None:
    key = _new_agent(engine, "cursor-a")
    first = _call(open_limit, key, "list_new_articles", {})
    assert "art1" in _ids(first)
    unacked = _call(open_limit, key, "list_new_articles", {})
    assert _ids(unacked) == _ids(first)  # no ack: same batch again

    _call(open_limit, key, "ack_cursor", {"cursor": first["next_cursor"]})
    _add_article(engine, "resume1")
    after = _call(open_limit, key, "list_new_articles", {})
    assert _ids(after) == ["resume1"]  # only what follows the acked position


# TC-10: another agent's cursor does not move mine
def test_cursors_are_independent(open_limit: str, engine: Engine) -> None:
    a, b = _new_agent(engine, "cursor-b1"), _new_agent(engine, "cursor-b2")
    page = _call(open_limit, a, "list_new_articles", {})
    _call(open_limit, a, "ack_cursor", {"cursor": page["next_cursor"]})
    assert _ids(_call(open_limit, a, "list_new_articles", {})) == []
    fresh = _call(open_limit, b, "list_new_articles", {})
    assert "art1" in _ids(fresh)  # first-run window, untouched by a's ack


def test_explicit_cursor_wins_and_is_not_stored(
    open_limit: str, engine: Engine
) -> None:
    key = _new_agent(engine, "cursor-c")
    page = _call(open_limit, key, "list_new_articles", {})
    explicit = _call(
        open_limit, key, "list_new_articles", {"cursor": page["next_cursor"]}
    )
    assert _ids(explicit) == []
    assert "art1" in _ids(_call(open_limit, key, "list_new_articles", {}))


def _call_raw(base: str, key: str | None, tool: str, args: dict[str, Any]) -> Any:
    async def go() -> Any:
        async with _client(base, key) as client:
            return await client.call_tool(tool, args)

    return _run(go())


# TC-16: forward-only, idempotent, validated
def test_ack_is_forward_only_idempotent_and_validated(
    open_limit: str, engine: Engine
) -> None:
    key = _new_agent(engine, "cursor-d")
    page = _call(open_limit, key, "list_new_articles", {})
    high = page["next_cursor"]
    assert _call(open_limit, key, "ack_cursor", {"cursor": high})["cursor"] == high
    assert _call(open_limit, key, "ack_cursor", {"cursor": high})["cursor"] == high
    from newsdock_api.domain.service import encode_cursor

    low = encode_cursor(0)
    assert _call(open_limit, key, "ack_cursor", {"cursor": low})["cursor"] == high

    bad = _call_raw(open_limit, key, "ack_cursor", {"cursor": "garbage!!"})
    assert bad.is_error and "invalid_cursor" in str(bad.content)


def test_anonymous_cannot_ack(engine: Engine) -> None:
    with _serve(Settings(auth_required=False, rate_limit_per_minute=0)) as base:
        result = _call_raw(base, None, "ack_cursor", {"cursor": "c2VxOjA="})
    assert result.is_error and "anonymous_agent" in str(result.content)
