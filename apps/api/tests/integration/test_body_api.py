"""TC-16, TC-17 (body-extraction AC-9, AC-10): `body` and `body_status` on the detail,
`include=body` on the list surfaces, through REST and MCP (Docker, side Postgres)."""

import asyncio
import socket
import threading
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import httpx
import httpx2
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from newsdock_db.testing import article, make_vec
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]

GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count",
}  # fmt: skip
HIT = {"score", "matched_by"}
# article id -> (body status, stored text); "D" has no body row at all
BODIES = {
    "A": ("ok", "Full text of article A."),
    "B": ("pending", None),
    "C": ("blocked_robots", None),
}


class FakeQueryEmbedder:
    def embed_query(self, query: str) -> list[float]:
        return make_vec(1.0, 0.0)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(eng) as session:
        session.add_all(
            [
                article("A", "Interest rates rise",
                        vec=make_vec(1.0, 0.0), tone_neg=9.0),
                article("B", "Interest rates explained", vec=make_vec(0.9, 0.1)),
                article("C", "Interest rates and banks", vec=make_vec(0.8, 0.2)),
                article("D", "Interest rates old story", vec=make_vec(0.7, 0.3)),
            ]
        )  # fmt: skip
        session.commit()
    with eng.begin() as conn:
        for key, (status, body) in BODIES.items():
            conn.execute(
                text(
                    "INSERT INTO article_bodies (url_hash, seq, status, text) "
                    "SELECT url_hash, seq, :s, :t FROM articles WHERE url_hash = :k"
                ),
                {"k": key, "s": status, "t": body},
            )
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def agent(engine: Engine) -> str:
    made = make_key()
    SqlAgentsRepo(engine).create_agent("body-agent", made, None)
    return made.raw


# --- REST -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client(engine: Engine) -> TestClient:
    return TestClient(create_app(Settings(auth_required=True, rate_limit_per_minute=0)))


def feed(client: TestClient, key: str, **params: Any) -> dict[str, dict[str, Any]]:
    response = client.get(
        "/api/articles", params=params, headers={"Authorization": f"Bearer {key}"}
    )
    assert response.status_code == 200, response.text
    return {a["article_id"]: a for a in response.json()["articles"]}


# TC-16 (AC-9)
@pytest.mark.parametrize(
    ("article_id", "status", "body"),
    [
        ("A", "ok", "Full text of article A."),
        ("B", "pending", None),
        ("C", "blocked_robots", None),
        ("D", "none", None),
    ],
)
def test_rest_detail_carries_body_and_status(
    client: TestClient, agent: str, article_id: str, status: str, body: str | None
) -> None:
    response = client.get(
        f"/api/articles/{article_id}", headers={"Authorization": f"Bearer {agent}"}
    )
    assert response.status_code == 200
    detail = response.json()
    assert (detail["body_status"], detail["body"]) == (status, body)


# TC-17 (AC-10)
def test_rest_feed_has_no_body_key_unless_asked(client: TestClient, agent: str) -> None:
    assert all(set(a) == GOLDEN for a in feed(client, agent).values())
    tone = feed(client, agent, include="tone_neg")
    assert all(set(a) == GOLDEN | {"tone_neg"} for a in tone.values())


def test_rest_include_body_adds_text_or_null(client: TestClient, agent: str) -> None:
    rows = feed(client, agent, include="body")
    assert all(set(a) == GOLDEN | {"body"} for a in rows.values())
    assert rows["A"]["body"] == "Full text of article A."
    assert [rows[k]["body"] for k in "BCD"] == [None, None, None]


def test_rest_body_mixes_with_tone_and_events(client: TestClient, agent: str) -> None:
    rows = feed(client, agent, include="body,tone_neg,events")
    assert set(rows["A"]) == GOLDEN | {"body", "tone_neg", "events"}
    assert rows["A"]["tone_neg"] == 9.0


@pytest.mark.parametrize("value", ["bogus", "body,bogus", "Body"])
def test_rest_unknown_include_is_a_422(
    client: TestClient, agent: str, value: str
) -> None:
    response = client.get(
        "/api/articles",
        params={"include": value},
        headers={"Authorization": f"Bearer {agent}"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_include"


# --- MCP ------------------------------------------------------------------------------
def _serve(settings: Settings) -> Generator[str, None, None]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, query_embedder=FakeQueryEmbedder()),
            host="127.0.0.1",
            port=port,
            log_level="warning",
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
def base(engine: Engine) -> Iterator[str]:
    yield from _serve(
        Settings(auth_required=True, rate_limit_per_minute=0, embedding_model="m1")
    )


def call(base: str, key: str, tool: str, args: dict[str, Any]) -> Any:
    async def go() -> Any:
        client = Client(
            streamable_http_client(
                f"{base}/mcp",
                http_client=httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {key}"}
                ),
            )
        )
        async with client:
            return await client.call_tool(tool, args)

    return asyncio.new_event_loop().run_until_complete(go())


def ok(base: str, key: str, tool: str, **args: Any) -> dict[str, Any]:
    result = call(base, key, tool, args)
    assert not result.is_error, result.content
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["article_id"]: a for a in payload["articles"]}


# TC-16 (AC-9)
def test_mcp_get_article_carries_body_and_status(base: str, agent: str) -> None:
    got = {k: ok(base, agent, "get_article", article_id=k) for k in "ABCD"}
    assert [(g["body_status"], g["body"]) for g in got.values()] == [
        ("ok", "Full text of article A."),
        ("pending", None),
        ("blocked_robots", None),
        ("none", None),
    ]


# TC-17 (AC-10)
@pytest.mark.parametrize("tool", ["search_articles", "list_new_articles"])
def test_mcp_list_tools_take_include_body(base: str, agent: str, tool: str) -> None:
    plain = ok(base, agent, tool)
    assert all(set(a) == GOLDEN for a in plain["articles"])
    got = rows(ok(base, agent, tool, include=["body", "tone_neg"]))
    assert set(got["A"]) == GOLDEN | {"body", "tone_neg"}
    assert got["A"]["body"] == "Full text of article A."
    assert got["D"]["body"] is None


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_mcp_semantic_search_include_body(base: str, agent: str, mode: str) -> None:
    got = rows(
        ok(base, agent, "semantic_search", query="interest rates", mode=mode,
           include=["body"])
    )  # fmt: skip
    assert set(got["A"]) == GOLDEN | HIT | {"body"}
    assert got["A"]["body"] == "Full text of article A."
    plain = ok(base, agent, "semantic_search", query="interest rates")
    assert all(set(a) == GOLDEN | HIT for a in plain["articles"])


@pytest.mark.parametrize("tool", ["search_articles", "list_new_articles"])
def test_mcp_unknown_include_is_still_invalid_include(
    base: str, agent: str, tool: str
) -> None:
    result = call(base, agent, tool, {"include": ["body", "bogus"]})
    assert result.is_error
    assert "invalid_include" in " ".join(getattr(c, "text", "") for c in result.content)


# TC-22 (body-extraction AC-13): the `scope` argument of semantic_search
def test_mcp_semantic_scope_adds_passage_and_rejects_unknown(
    base: str, agent: str
) -> None:
    plain = ok(base, agent, "semantic_search", query="interest rates", scope="titles")
    assert all("passage" not in a for a in plain["articles"])
    every = ok(base, agent, "semantic_search", query="interest rates", scope="all")
    assert all("passage" in a for a in every["articles"])  # null: no passages here
    result = call(base, agent, "semantic_search", {"query": "x", "scope": "text"})
    assert result.is_error
    assert "invalid_scope" in " ".join(getattr(c, "text", "") for c in result.content)
