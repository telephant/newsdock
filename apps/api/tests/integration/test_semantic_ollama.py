"""TC-7 (AC-7): vector search finds a paraphrase that keyword search misses.

Needs Docker and a real Ollama with `nomic-embed-text` (`ollama pull
nomic-embed-text`); skipped with a message otherwise. Run with
From the repository root: `uv run pytest -m "docker and ollama"
apps/api/tests/integration/test_semantic_ollama.py`.
"""

import asyncio
import json
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from mcp import Client
from newsdock_api.adapters.query_embedder import OllamaQueryEmbedder
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_api.config import Settings
from newsdock_api.domain.semantic import SearchFilters
from newsdock_db.engine import make_engine
from newsdock_db.testing import article
from newsdock_embedding import document_text, embed
from sqlalchemy import Engine
from sqlalchemy.orm import Session

pytestmark = [pytest.mark.docker, pytest.mark.ollama]

ROOT = Path(__file__).resolve().parents[4]
OLLAMA = "http://127.0.0.1:11434"
MODEL = "nomic-embed-text"
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

TITLES = {
    "rates": "Central bank lifts borrowing costs",
    "fire": "Thousands flee as blaze spreads across hills",
    "oil": "Crude slides to three-month low on weak demand",
    "vote": "Opposition wins parliamentary majority in vote",
    "jobs": "Software firm cuts 2,000 jobs in restructuring",
}


def _ollama_has_the_model() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=3) as response:
            names = [m["name"] for m in json.load(response)["models"]]
    except OSError:
        return False
    return any(n.split(":")[0] == MODEL for n in names)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    if not _ollama_has_the_model():
        pytest.skip(f"Ollama with {MODEL} is not reachable at {OLLAMA}")
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    vectors = embed(
        [document_text(t, DOC_PREFIX) for t in TITLES.values()],
        model=MODEL,
        url=OLLAMA,
        timeout=60.0,
    )
    with Session(eng) as session:
        session.add_all(
            article(key, title, vec=vec, model=MODEL)
            for (key, title), vec in zip(TITLES.items(), vectors, strict=True)
        )
        session.commit()
    yield eng
    eng.dispose()


def test_vector_search_finds_the_paraphrase_that_keyword_search_misses(
    engine: Engine,
) -> None:
    query = "interest rate hike"
    embedder = OllamaQueryEmbedder(
        url=OLLAMA, model=MODEL, dimension=768, prefix=QUERY_PREFIX, timeout=60.0
    )

    hits = SqlSemanticRepo(engine).vector_leg(
        vector=embedder.embed_query(query),
        model=MODEL,
        filters=SearchFilters(),
        limit=3,
    )
    keyword = SqlArticleRepo(engine).search(
        time_from=None, time_to=None, theme=None, domain=None, text=query, limit=10
    )

    assert hits[0].id == "rates"  # the paraphrase is the nearest title
    assert "rates" not in [a.article_id for a in keyword]  # substring search misses it


@pytest.fixture(scope="module")
def live_url(engine: Engine) -> Iterator[str]:
    """The real app with the real query embedder (no fake), auth off."""
    from newsdock_api.adapters.http import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = Settings(
        auth_required=False,
        rate_limit_per_minute=0,
        embedding_model=MODEL,
        embedding_ollama_url=OLLAMA,
    )
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
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def _call(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        async with Client(f"{url}/mcp") as client:
            result = await client.call_tool(tool, args)
            assert not result.is_error, result.content
            assert isinstance(result.structured_content, dict)
            return result.structured_content

    return asyncio.new_event_loop().run_until_complete(go())


def test_the_paraphrase_is_found_through_the_mcp_tool(live_url: str) -> None:
    query = "interest rate hike"
    vector = _call(live_url, "semantic_search", {"query": query, "mode": "vector"})
    hybrid = _call(live_url, "semantic_search", {"query": query})
    keyword = _call(live_url, "search_articles", {"text": query})

    assert vector["articles"][0]["article_id"] == "rates"
    assert hybrid["articles"][0]["article_id"] == "rates" and not hybrid["degraded"]
    assert "rates" not in [a["article_id"] for a in keyword["articles"]]
