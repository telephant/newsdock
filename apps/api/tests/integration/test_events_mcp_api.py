"""TC-15, TC-17, TC-19, TC-20 (MCP halves): `include=["events"]` through the MCP
tools of a live app (Docker, side Postgres)."""

import asyncio
import socket
import threading
import time
from collections.abc import Generator, Iterator
from datetime import UTC, date, datetime
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
from newsdock_db.models import Event, Mention
from newsdock_db.testing import article, make_vec
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
ADDED = datetime(2026, 11, 2, 11, tzinfo=UTC)

GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count",
}  # fmt: skip
HIT = {"score", "matched_by"}
EVENT_KEYS = {
    "event_id", "date", "cameo_code", "cameo_root", "goldstein", "quad_class",
    "num_mentions", "num_sources", "avg_tone", "actor1", "actor2", "location",
    "source_url", "mention_count",
}  # fmt: skip


class FakeQueryEmbedder:
    def embed_query(self, query: str) -> list[float]:
        return make_vec(1.0, 0.0)


def _event(event_id: int, num_mentions: int) -> Event:
    return Event(
        event_id=event_id, event_date=date(2026, 11, 2), is_root=False,
        cameo_code="040", cameo_base="040", cameo_root="04", quad_class=1,
        goldstein=1.5, num_mentions=num_mentions, num_sources=2, num_articles=3,
        avg_tone=-2.5, actor1_code="GOV", geo_name="Paris, France", geo_country="FR",
        date_added=ADDED, source_url=f"https://e.com/{event_id}", source_url_hash="A",
    )  # fmt: skip


def _mention(event_id: int, url_hash: str, *, derived: bool = False) -> Mention:
    return Mention(
        event_id=event_id,
        url_hash=url_hash,
        url=f"https://e.com/{url_hash}",
        mention_time=ADDED,
        derived=derived,
    )


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE events, mentions"))
    with Session(eng) as session:
        session.add_all(
            [
                article("A", "Protest over interest rates in Paris",
                        vec=make_vec(1.0, 0.0), tone=-4.0, tone_neg=9.5),
                article("B", "Interest rates explained for beginners",
                        vec=make_vec(0.9, 0.1), tone=1.0, tone_neg=2.0),
            ]
        )  # fmt: skip
        session.commit()
        session.add_all([_event(1, 5), _event(2, 9), _event(3, 1)])
        session.add_all(
            [
                _mention(1, "A"), _mention(2, "A"), _mention(2, "X"),
                # event 3 is mentioned by a copy of A only: the sink's derived row
                _mention(3, "X3"), _mention(3, "A", derived=True),
            ]
        )  # fmt: skip
        session.commit()
    yield eng
    eng.dispose()


def _serve(settings: Settings) -> Generator[str, None, None]:
    from newsdock_api.adapters.http import create_app

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
    settings = Settings(
        auth_required=True, rate_limit_per_minute=0, embedding_model="m1"
    )
    yield from _serve(settings)


@pytest.fixture(scope="module")
def key(engine: Engine) -> str:
    made = make_key()
    SqlAgentsRepo(engine).create_agent("events-agent", made, None)
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


def rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["article_id"]: a for a in payload["articles"]}


# --- TC-15 (AC-9): every list tool takes include=["events"] --------------------------
def test_search_articles_include_events(base: str, key: str) -> None:
    got = rows(ok(base, key, "search_articles", include=["events"]))
    assert set(got["A"]) == GOLDEN | {"events"}
    events = got["A"]["events"]
    assert [e["event_id"] for e in events] == [2, 1, 3]
    assert set(events[0]) == EVENT_KEYS
    assert events[0]["mention_count"] == 2 and events[0]["num_mentions"] == 9
    assert events[0]["location"]["country"] == "FR"


def test_list_new_articles_include_events_keeps_the_cursor(base: str, key: str) -> None:
    plain = ok(base, key, "list_new_articles")
    asked = ok(base, key, "list_new_articles", include=["events"])
    assert asked["next_cursor"] == plain["next_cursor"]
    assert [a["article_id"] for a in asked["articles"]] == [
        a["article_id"] for a in plain["articles"]
    ]
    assert [e["event_id"] for e in rows(asked)["A"]["events"]] == [2, 1, 3]


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_semantic_search_include_events(base: str, key: str, mode: str) -> None:
    got = ok(
        base, key, "semantic_search", query="interest rates", mode=mode,
        include=["events"],
    )  # fmt: skip
    found = rows(got)
    assert set(found["A"]) == GOLDEN | HIT | {"events"}
    assert [e["event_id"] for e in found["A"]["events"]] == [2, 1, 3]


def test_get_article_always_carries_events(base: str, key: str) -> None:
    detail = ok(base, key, "get_article", article_id="A")
    assert [e["event_id"] for e in detail["events"]] == [2, 1, 3]
    assert ok(base, key, "get_article", article_id="B")["events"] == []


# --- TC-19 (AC-12) -------------------------------------------------------------------
def test_an_article_without_events_gets_an_empty_list(base: str, key: str) -> None:
    got = rows(ok(base, key, "search_articles", include=["events"]))
    assert got["B"]["events"] == []


# --- TC-17 (AC-10): nothing changes without it ---------------------------------------
def test_default_and_tone_only_responses_have_no_events_key(
    base: str, key: str
) -> None:
    for tool in ("search_articles", "list_new_articles"):
        plain = ok(base, key, tool)
        assert all(set(a) == GOLDEN for a in plain["articles"])
        tone = ok(base, key, tool, include=["tone_neg"])
        assert all(set(a) == GOLDEN | {"tone_neg"} for a in tone["articles"])
    hits = ok(base, key, "semantic_search", query="interest rates")
    assert all(set(a) == GOLDEN | HIT for a in hits["articles"])


def test_events_and_tone_together(base: str, key: str) -> None:
    got = rows(ok(base, key, "search_articles", include=["tone_neg", "events"]))
    assert set(got["A"]) == GOLDEN | {"tone_neg", "events"}


# --- TC-20 (AC-13): unknown names ----------------------------------------------------
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
    assert "invalid_include" in error_text(base, key, tool, include=["bogus"], **extra)
    mixed = error_text(base, key, tool, include=["events", "bogus"], **extra)
    assert "invalid_include" in mixed


# --- TC-11 (AC-9), TC-4: an event reached through a copy shows on the canonical ------
def test_event_of_a_copy_shows_on_the_canonical_with_real_mention_count(
    base: str, key: str
) -> None:
    listed = rows(ok(base, key, "search_articles", include=["events"]))["A"]["events"]
    detail = ok(base, key, "get_article", article_id="A")["events"]
    for events in (listed, detail):
        third = next(e for e in events if e["event_id"] == 3)
        assert third["mention_count"] == 1  # the copy's own mention, not the link
