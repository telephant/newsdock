"""TC-9, TC-11, TC-13, and TC-6/TC-10/TC-12 through the MCP tool (Docker).

A live app on a side Postgres, an MCP client with an agent key, hand-made vectors,
and a fake query embedder that can be switched off (Ollama down).
"""

import asyncio
import socket
import threading
import time
from collections.abc import Generator, Iterator
from datetime import timedelta
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
from newsdock_api.domain.semantic import EmbeddingUnavailable
from newsdock_db.engine import make_engine
from newsdock_db.testing import NOW, article, make_vec
from sqlalchemy import Engine
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


class FakeQueryEmbedder:
    """Every query lands on the first axis; `down` simulates Ollama being off."""

    def __init__(self) -> None:
        self.down = False
        self.calls = 0

    def embed_query(self, query: str) -> list[float]:
        self.calls += 1
        if self.down:
            raise EmbeddingUnavailable("ollama down")
        return make_vec(1.0, 0.0)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with Session(eng) as session:
        session.add_all(
            [
                article("A", "Central bank raises interest rates", domain="a.com",
                        vec=make_vec(1.0, 0.0), themes=["ECON_RATES"]),
                article("B", "Wildfire spreads across the hills", domain="a.com",
                        vec=make_vec(0.8, 0.6), themes=["ENV_FIRE"]),
                article("C", "Interest rates explained for beginners", domain="a.com"),
                article("D", "Opposition wins the vote", domain="b.com",
                        vec=make_vec(0.0, 1.0), themes=["GOV_ELECTION"],
                        published_at=NOW - timedelta(days=3)),
                article("E", "Old model row", domain="a.com",
                        vec=make_vec(1.0, 0.0), model="old-model"),
            ]
        )  # fmt: skip
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def fake() -> FakeQueryEmbedder:
    return FakeQueryEmbedder()


def _serve(settings: Settings, fake: FakeQueryEmbedder) -> Generator[str, None, None]:
    from newsdock_api.adapters.http import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, query_embedder=fake),
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
def base(engine: Engine, fake: FakeQueryEmbedder) -> Iterator[str]:
    settings = Settings(
        auth_required=True,
        rate_limit_per_minute=0,
        embedding_model="m1",
        search_page_default=20,
    )
    yield from _serve(settings, fake)


@pytest.fixture(scope="module")
def key(engine: Engine) -> str:
    made = make_key()
    SqlAgentsRepo(engine).create_agent("semantic-agent", made, None)
    return made.raw


def _client(base: str, raw_key: str | None) -> Client:
    headers = {"Authorization": f"Bearer {raw_key}"} if raw_key else {}
    return Client(
        streamable_http_client(
            f"{base}/mcp", http_client=httpx2.AsyncClient(headers=headers)
        )
    )


def call(base: str, raw_key: str | None, tool: str, args: dict[str, Any]) -> Any:
    async def go() -> Any:
        async with _client(base, raw_key) as client:
            return await client.call_tool(tool, args)

    return asyncio.new_event_loop().run_until_complete(go())


def search(base: str, key: str, **args: Any) -> dict[str, Any]:
    result = call(base, key, "semantic_search", args)
    assert not result.is_error, result.content
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def ids(payload: dict[str, Any]) -> list[str]:
    return [a["article_id"] for a in payload["articles"]]


def test_the_tool_is_listed(base: str, key: str) -> None:
    async def go() -> list[str]:
        async with _client(base, key) as client:
            return sorted(t.name for t in (await client.list_tools()).tools)

    names = asyncio.new_event_loop().run_until_complete(go())
    assert "semantic_search" in names


# TC-6 (AC-6) through the tool: nearest first, similarity as the score
def test_vector_mode_orders_by_similarity(
    base: str, key: str, fake: FakeQueryEmbedder
) -> None:
    fake.down = False
    got = search(base, key, query="anything", mode="vector")
    assert (got["mode"], got["degraded"]) == ("vector", False)
    assert ids(got) == ["A", "B", "D"]  # E is another model, C has no vector
    assert [a["score"] for a in got["articles"]] == pytest.approx([1.0, 0.8, 0.0])
    assert all(a["matched_by"] == ["vector"] for a in got["articles"])
    assert "seq" not in got["articles"][0]  # the raw cursor basis stays hidden


# TC-12 (AC-11) through the tool: vectors from another model are never compared
def test_rows_of_another_model_are_never_matched_by_vector(
    base: str,
    key: str,
    fake: FakeQueryEmbedder,
) -> None:
    fake.down = False
    assert "E" not in ids(search(base, key, query="old model row", mode="vector"))
    # the keyword leg does not use embeddings, so a title match is still fine
    hybrid = search(base, key, query="old model row", mode="hybrid")
    found = {a["article_id"]: a["matched_by"] for a in hybrid["articles"]}
    assert found.get("E") == ["keyword"]


# TC-9 (AC-8): hybrid fuses both legs
def test_hybrid_ranks_the_article_found_by_both_legs_first(
    base: str,
    key: str,
    fake: FakeQueryEmbedder,
) -> None:
    fake.down = False
    got = search(base, key, query="interest rates")  # hybrid is the default
    assert got["mode"] == "hybrid" and got["degraded"] is False
    assert ids(got)[0] == "A"
    matched = {a["article_id"]: a["matched_by"] for a in got["articles"]}
    assert matched["A"] == ["vector", "keyword"]
    assert matched["B"] == ["vector"]
    assert matched["C"] == ["keyword"]


# TC-10 (AC-9) through the tool: filters apply in both modes
def test_filters_apply_in_both_modes(
    base: str, key: str, fake: FakeQueryEmbedder
) -> None:
    fake.down = False
    for mode in ("vector", "hybrid"):
        only_b = search(base, key, query="interest rates", mode=mode, domain="b.com")
        assert set(ids(only_b)) <= {"D"}
        if mode == "vector":
            assert ids(only_b) == ["D"]
        prefix = search(base, key, query="interest rates", mode=mode, theme="ECON_*")
        assert set(ids(prefix)) == {"A"}
        recent = search(
            base,
            key,
            query="interest rates",
            mode=mode,
            time_from=(NOW - timedelta(days=1)).isoformat(),
        )
        assert "D" not in ids(recent)


def test_limit_is_respected(base: str, key: str, fake: FakeQueryEmbedder) -> None:
    fake.down = False
    assert len(search(base, key, query="x", mode="vector", limit=2)["articles"]) == 2


# TC-20 (AC-6): bad input is refused before any embedding call
def test_invalid_input_is_refused_before_embedding(
    base: str,
    key: str,
    fake: FakeQueryEmbedder,
) -> None:
    fake.down = False
    before = fake.calls
    for args in ({"query": "   "}, {"query": "q", "mode": "keyword"}):
        result = call(base, key, "semantic_search", args)
        assert result.is_error and "invalid_query" in str(result.content), args
    too_long = call(base, key, "semantic_search", {"query": "x" * 501})
    assert too_long.is_error and "invalid_query" in str(too_long.content)
    assert fake.calls == before


# TC-11 (AC-10): Ollama down
def test_ollama_down_vector_errors_and_hybrid_degrades(
    base: str,
    key: str,
    fake: FakeQueryEmbedder,
) -> None:
    fake.down = True
    try:
        vector = call(
            base, key, "semantic_search", {"query": "interest rates", "mode": "vector"}
        )
        assert vector.is_error and "embedding_unavailable" in str(vector.content)
        assert "ollama down" not in str(vector.content)  # no internals in the message

        hybrid = search(base, key, query="interest rates", mode="hybrid")
        assert hybrid["degraded"] is True
        assert set(ids(hybrid)) == {"A", "C"}  # the keyword matches
        assert all(a["matched_by"] == ["keyword"] for a in hybrid["articles"])

        plain = call(base, key, "search_articles", {"text": "interest"})
        assert not plain.is_error  # the keyword search is unaffected
    finally:
        fake.down = False


# TC-13 (AC-12): same auth and rate limit as every other tool
def test_a_missing_or_revoked_key_is_refused(
    base: str, key: str, engine: Engine
) -> None:
    with pytest.raises(BaseException):  # noqa: B017, PT011 — the client sees the 401
        call(base, None, "semantic_search", {"query": "q"})
    revoked = make_key()
    repo = SqlAgentsRepo(engine)
    agent = repo.create_agent("revoked-agent", revoked, None)
    from newsdock_api.domain.agents import ALL

    repo.revoke_key(agent.id, agent.key_id, ALL)
    with pytest.raises(BaseException):  # noqa: B017, PT011
        call(base, revoked.raw, "semantic_search", {"query": "q"})


def test_the_rate_limit_applies_to_the_tool(
    engine: Engine, fake: FakeQueryEmbedder
) -> None:
    fresh = make_key()
    SqlAgentsRepo(engine).create_agent("limited-agent", fresh, None)
    settings = Settings(
        auth_required=True, rate_limit_per_minute=8, embedding_model="m1"
    )
    gen = _serve(settings, fake)
    limited_base = next(gen)
    try:
        outcomes = []
        for _ in range(10):  # each tool call is several HTTP requests
            try:
                outcomes.append(
                    call(limited_base, fresh.raw, "semantic_search", {"query": "q"})
                )
            except BaseException:  # noqa: BLE001 — a 429 reaches the client as an error
                outcomes.append(None)
        assert outcomes[0] is not None and not outcomes[0].is_error
        assert None in outcomes  # the limit kicked in
    finally:
        gen.close()
