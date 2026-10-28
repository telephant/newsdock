"""TC-7 (AC-7): vector search finds a paraphrase that keyword search misses.

Needs Docker and a real Ollama with `nomic-embed-text` (`ollama pull
nomic-embed-text`); skipped with a message otherwise. Run with
From the repository root: `uv run pytest -m "docker and ollama"
apps/api/tests/integration/test_semantic_ollama.py`.
"""

import json
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.query_embedder import OllamaQueryEmbedder
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
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
