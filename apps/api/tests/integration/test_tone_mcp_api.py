"""TC-2, TC-5, TC-6, TC-7, TC-9, TC-10, TC-18 (MCP halves): `include` and
`min_negativity` through the MCP tools of a live app (Docker, side Postgres)."""

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
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_api.domain.semantic import EmbeddingUnavailable
from newsdock_db.engine import make_engine
from newsdock_db.testing import article, make_vec
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]

# The keys of an article in a default response before this feature (AC-1).
GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count",
}  # fmt: skip
HIT = {"score", "matched_by"}
TONE = {"tone", "tone_pos", "tone_neg", "tone_polarity"}
STORED = {  # tone_neg of each row; E has none
    "A": 9.5, "B": 3.0, "C": 12.5, "D": 8.0, "E": None, "F": 9.7,
}  # fmt: skip


class FakeQueryEmbedder:
    def __init__(self) -> None:
        self.down = False

    def embed_query(self, query: str) -> list[float]:
        if self.down:
            raise EmbeddingUnavailable("ollama down")
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
                article("A", "Central bank raises interest rates",
                        vec=make_vec(1.0, 0.0), themes=["ECON_RATES"], tone=-4.0,
                        tone_pos=1.5, tone_neg=9.5, tone_polarity=11.0),
                article("B", "Wildfire spreads across the hills",
                        vec=make_vec(0.8, 0.6), tone=2.0, tone_neg=3.0),
                article("C", "Interest rates tumble sharply",
                        vec=make_vec(0.6, 0.8), tone=-12.0, tone_neg=12.5),
                article("D", "Opposition wins the vote",
                        vec=make_vec(0.0, 1.0), tone=-8.0, tone_neg=8.0),
                article("E", "Interest rates explained for beginners",
                        vec=make_vec(1.0, 0.0)),
                article("F", "Rates outlook darkens",
                        vec=make_vec(0.9, 0.1), tone=-9.7, tone_neg=9.7),
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
        auth_required=True, rate_limit_per_minute=0, embedding_model="m1",
        search_page_default=20,
    )  # fmt: skip
    yield from _serve(settings, fake)


@pytest.fixture(scope="module")
def key(engine: Engine) -> str:
    made = make_key()
    SqlAgentsRepo(engine).create_agent("tone-agent", made, None)
    return made.raw


def call(base: str, raw_key: str, tool: str, args: dict[str, Any]) -> Any:
    async def go() -> Any:
        client = Client(
            streamable_http_client(
                f"{base}/mcp",
                http_client=httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {raw_key}"}
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


def error_text(base: str, key: str, tool: str, **args: Any) -> str:
    result = call(base, key, tool, args)
    assert result.is_error, "expected a tool error"
    return " ".join(getattr(c, "text", "") for c in result.content)


def ids(payload: dict[str, Any]) -> set[str]:
    return {a["article_id"] for a in payload["articles"]}


# --- TC-2 (AC-1): default payloads keep exactly today's keys -------------------------
def test_default_responses_have_exactly_the_golden_keys(
    base: str, key: str, fake: FakeQueryEmbedder
) -> None:
    fake.down = False
    searched = ok(base, key, "search_articles")
    assert ids(searched) == set("ABCDEF")
    assert all(set(a) == GOLDEN for a in searched["articles"])

    listed = ok(base, key, "list_new_articles")
    assert listed["articles"] and all(set(a) == GOLDEN for a in listed["articles"])

    for mode in ("vector", "hybrid"):
        hits = ok(base, key, "semantic_search", query="interest rates", mode=mode)
        assert hits["articles"]
        assert all(set(a) == GOLDEN | HIT for a in hits["articles"])


# --- TC-5 (AC-2) --------------------------------------------------------------------
def test_search_articles_include_one_field(base: str, key: str) -> None:
    got = ok(base, key, "search_articles", include=["tone_neg"])
    by_id = {a["article_id"]: a for a in got["articles"]}
    assert set(by_id) == set("ABCDEF")
    for name, stored in STORED.items():
        assert set(by_id[name]) == GOLDEN | {"tone_neg"}
        assert by_id[name]["tone_neg"] == stored  # null for E


# --- TC-6 (AC-3) --------------------------------------------------------------------
def test_list_new_articles_include_keeps_the_page_and_cursor(
    base: str, key: str
) -> None:
    plain = ok(base, key, "list_new_articles", limit=3)
    with_tone = ok(
        base, key, "list_new_articles", limit=3, include=["tone", "tone_neg"]
    )
    assert [a["article_id"] for a in with_tone["articles"]] == [
        a["article_id"] for a in plain["articles"]
    ]
    assert with_tone["next_cursor"] == plain["next_cursor"]
    assert all(set(a) == GOLDEN | {"tone", "tone_neg"} for a in with_tone["articles"])
    assert all(set(a) == GOLDEN for a in plain["articles"])


# --- TC-7 (AC-4) --------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_semantic_search_include(
    base: str, key: str, fake: FakeQueryEmbedder, mode: str
) -> None:
    fake.down = False
    got = ok(
        base, key, "semantic_search", query="interest rates", mode=mode,
        include=["tone_neg"],
    )  # fmt: skip
    assert got["articles"]
    for a in got["articles"]:
        assert set(a) == GOLDEN | HIT | {"tone_neg"}
        assert a["tone_neg"] == STORED[a["article_id"]]


# --- TC-9 (AC-6): unknown include names ----------------------------------------------
@pytest.mark.parametrize(
    ("tool", "extra"),
    [
        ("search_articles", {}),
        ("list_new_articles", {}),
        ("semantic_search", {"query": "interest rates"}),
    ],
)
def test_unknown_include_name_is_a_named_tool_error(
    base: str, key: str, tool: str, extra: dict[str, Any]
) -> None:
    assert "invalid_include" in error_text(base, key, tool, include=["tone_x"], **extra)
    assert "invalid_include" in error_text(base, key, tool, include=[""], **extra)
    # a bare string is not a list: the tool's own validation refuses it
    error_text(base, key, tool, include="tone_neg", **extra)


# --- TC-10 (AC-7) -------------------------------------------------------------------
def test_a_row_without_tone_is_null_when_asked_and_absent_otherwise(
    base: str, key: str
) -> None:
    asked = ok(
        base, key, "search_articles", text="explained", include=["tone", "tone_neg"]
    )
    (row,) = asked["articles"]
    assert row["article_id"] == "E"
    assert row["tone"] is None and row["tone_neg"] is None
    plain = ok(base, key, "search_articles", text="explained")
    assert not TONE & set(plain["articles"][0])


# --- AC-9 / AC-10 / AC-14 through the tools -----------------------------------------
def test_min_negativity_on_search_articles(base: str, key: str) -> None:
    assert ids(ok(base, key, "search_articles", min_negativity=8)) == set("ACDF")
    assert ids(ok(base, key, "search_articles", min_negativity=9.7)) == set("CF")
    assert ids(ok(base, key, "search_articles", min_negativity=8, theme="ECON_*")) == {
        "A"
    }
    assert ids(ok(base, key, "search_articles", min_negativity=8, text="rates")) == set(
        "ACF"
    )


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_min_negativity_on_semantic_search(
    base: str, key: str, fake: FakeQueryEmbedder, mode: str
) -> None:
    fake.down = False
    got = ok(
        base, key, "semantic_search", query="interest rates", mode=mode,
        min_negativity=8, include=["tone_neg"],
    )  # fmt: skip
    assert got["articles"]
    assert all(
        a["tone_neg"] is not None and a["tone_neg"] >= 8 for a in got["articles"]
    )
    assert ids(got) <= set("ACDF")


def test_hybrid_keeps_filtering_when_the_embedder_is_down(
    base: str, key: str, fake: FakeQueryEmbedder
) -> None:
    fake.down = True
    try:
        got = ok(
            base, key, "semantic_search", query="interest rates", mode="hybrid",
            min_negativity=8, include=["tone_neg"],
        )  # fmt: skip
    finally:
        fake.down = False
    assert got["degraded"] is True
    assert ids(got) == {"A", "C"}  # keyword matches; E has no tone_neg
    assert all(a["tone_neg"] >= 8 for a in got["articles"])


# --- TC-18 (AC-13): bad min_negativity -----------------------------------------------
@pytest.mark.parametrize(
    ("tool", "extra"),
    [("search_articles", {}), ("semantic_search", {"query": "interest rates"})],
)
def test_out_of_range_min_negativity_is_invalid_filter(
    base: str, key: str, tool: str, extra: dict[str, Any]
) -> None:
    for bad in (101, -1, 100.1, -0.5):
        assert "invalid_filter" in error_text(
            base, key, tool, min_negativity=bad, **extra
        )


@pytest.mark.parametrize(
    ("tool", "extra"),
    [("search_articles", {}), ("semantic_search", {"query": "interest rates"})],
)
@pytest.mark.parametrize("bad", ["abc", "8", True])
def test_non_numbers_fail_the_tools_own_validation(
    base: str, key: str, tool: str, extra: dict[str, Any], bad: Any
) -> None:
    error_text(base, key, tool, min_negativity=bad, **extra)
