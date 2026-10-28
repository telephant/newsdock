"""TC-15 and TC-16 (AC-14): recall@5 of keyword, vector and hybrid search.

A hand-written corpus (`corpus.json`, 40 titles, 8 topics) and labelled queries
(`queries.json`) are loaded into a throwaway Postgres; each query is run through
the substring search `search_articles` uses, the full-text leg, the vector leg and
the hybrid fusion. The run prints the numbers and asserts no threshold (AC-14: measure
first). TC-15 uses a deterministic fake embedder, so it checks that the harness runs;
TC-16 uses the real model (`make eval-search`) and is read by the owner.
"""

import json
import urllib.request
from collections.abc import Iterator, Sequence
from pathlib import Path
from statistics import mean
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.query_embedder import OllamaQueryEmbedder
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_api.config import Settings
from newsdock_api.domain.semantic import QueryEmbedder, SearchFilters, SemanticService
from newsdock_db.engine import make_engine
from newsdock_db.testing import article
from newsdock_embedding import document_text, embed
from newsdock_embedding.testing import FakeOllama
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[4]
K = 5
MODEL = "nomic-embed-text"
OLLAMA = "http://127.0.0.1:11434"
FAKE_URL = "http://ollama.test:11434"
METHODS = ("keyword", "fulltext", "vector", "hybrid")
LABELS = {
    "keyword": "keyword (search_articles substring)",
    "fulltext": "fulltext (hybrid's keyword leg)",
    "vector": "vector",
    "hybrid": "hybrid",
}


def recall_at_k(expected: Sequence[str], got: Sequence[str], k: int = K) -> float:
    """Share of the expected ids found among the first k results."""
    wanted = set(expected)
    if not wanted:
        raise ValueError("a query needs at least one expected article")
    return len(wanted & set(got[:k])) / len(wanted)


def reciprocal_rank(expected: Sequence[str], got: Sequence[str]) -> float:
    """1 / rank of the first expected id in the results; 0 when none is there."""
    wanted = set(expected)
    for rank, article_id in enumerate(got, start=1):
        if article_id in wanted:
            return 1.0 / rank
    return 0.0


def test_reciprocal_rank_is_one_over_the_first_hit() -> None:
    assert reciprocal_rank(["a", "b"], ["a", "x"]) == 1.0
    assert reciprocal_rank(["a", "b"], ["x", "b", "a"]) == 0.5
    assert reciprocal_rank(["a"], ["x", "y"]) == 0.0
    assert reciprocal_rank(["a"], []) == 0.0


def test_recall_at_k_counts_expected_ids_in_the_top_k() -> None:
    assert recall_at_k(["a", "b"], ["a", "x", "b"]) == 1.0
    assert recall_at_k(["a", "b"], ["a", "x", "y"]) == 0.5
    assert recall_at_k(["a", "b"], ["x", "y", "z"]) == 0.0
    assert recall_at_k(["a"], ["x", "y", "z", "q", "r", "a"], k=5) == 0.0  # sixth place
    assert recall_at_k(["a", "a"], ["a"]) == 1.0  # duplicates in the label count once


def test_recall_at_k_needs_something_to_find() -> None:
    with pytest.raises(ValueError):
        recall_at_k([], ["a"])


def test_the_labelled_queries_point_at_articles_in_the_corpus() -> None:
    corpus = {c["id"] for c in _load("corpus.json")}
    queries = _load("queries.json")
    assert len(corpus) == len(_load("corpus.json")) == 40
    assert len(queries) == 12
    for q in queries:
        assert q["expected"] and set(q["expected"]) <= corpus, q["query"]


def _load(name: str) -> list[dict[str, Any]]:
    data = json.loads((HERE / name).read_text())
    assert isinstance(data, list)
    return data


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def run_eval(
    engine: Engine,
    *,
    label: str,
    doc_prefix: str,
    query_prefix: str,
    client: httpx.Client | None,
    url: str,
) -> dict[str, float]:
    """Embed and load the corpus, run every query through the four methods, print."""
    corpus, queries = _load("corpus.json"), _load("queries.json")
    settings = Settings()
    vectors = embed(
        [document_text(c["title"], doc_prefix) for c in corpus],
        model=MODEL,
        url=url,
        timeout=120.0,
        client=client,
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(engine) as session:
        session.add_all(
            article(c["id"], c["title"], vec=v, model=MODEL)
            for c, v in zip(corpus, vectors, strict=True)
        )
        session.commit()

    embedder: QueryEmbedder = OllamaQueryEmbedder(
        url=url, model=MODEL, dimension=768, prefix=query_prefix, timeout=120.0,
        client=client,
    )  # fmt: skip
    repo = SqlSemanticRepo(engine, ef_search=settings.semantic_ef_search)
    service = SemanticService(
        repo,
        embedder,
        model=MODEL,
        candidates=settings.semantic_candidates,
        rrf_k=settings.semantic_rrf_k,
        max_query_length=settings.semantic_query_max_length,
        default_limit=K,
        max_limit=100,
    )
    plain = SqlArticleRepo(engine)

    per_query: dict[str, list[tuple[str, float, float]]] = {m: [] for m in METHODS}
    for q in queries:
        text_query, expected = q["query"], q["expected"]
        found = {
            "keyword": [
                a.article_id
                for a in plain.search(
                    time_from=None,
                    time_to=None,
                    theme=None,
                    domain=None,
                    text=text_query,
                    limit=K,
                )  # fmt: skip
            ],
            "fulltext": [
                h.id
                for h in repo.keyword_leg(
                    query=text_query, filters=SearchFilters(), limit=K
                )
            ],
            "vector": [
                a.article_id
                for a in service.search(text_query, mode="vector", limit=K).articles
            ],
            "hybrid": [
                a.article_id
                for a in service.search(text_query, mode="hybrid", limit=K).articles
            ],
        }
        for method in METHODS:
            per_query[method].append(
                (q["kind"], recall_at_k(expected, found[method]),
                 reciprocal_rank(expected, found[method]))
            )  # fmt: skip

    scores = {m: mean(r for _, r, _ in per_query[m]) for m in METHODS}
    ranks = {m: mean(rr for _, _, rr in per_query[m]) for m in METHODS}
    kinds = sorted({q["kind"] for q in queries})
    print(
        f"\n== recall@{K} [{label}]: {len(queries)} queries, {len(corpus)} articles, "
        f"rrf_k={settings.semantic_rrf_k}, candidates={settings.semantic_candidates}"
    )
    print(f"  {'':<38} recall@{K}   MRR")
    for method in METHODS:
        print(f"  {LABELS[method]:<38} {scores[method]:.3f}    {ranks[method]:.3f}")
    print("  by kind of query (recall@5):")
    for kind in kinds:
        row = "  ".join(
            f"{m} {mean(r for k, r, _ in per_query[m] if k == kind):.2f}"
            for m in METHODS
        )
        print(f"    {kind:<11} {row}")
    return scores


# TC-15 (AC-14): the harness runs and prints three recalls, with a fake embedder
@pytest.mark.docker
def test_the_eval_prints_recall_for_keyword_vector_and_hybrid(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeOllama()
    with httpx.Client(transport=fake.transport()) as client:
        scores = run_eval(
            engine,
            label="fake embedder",
            doc_prefix="search_document: ",
            query_prefix="search_query: ",
            client=client,
            url=FAKE_URL,
        )
    out = capsys.readouterr().out
    for method in ("keyword", "vector", "hybrid"):
        assert LABELS[method] in out
    assert set(scores) == set(METHODS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())
    # no threshold on quality (AC-14), but the baselines must have found something
    assert scores["keyword"] > 0.0 and scores["fulltext"] > 0.0


def _ollama_has_the_model() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=3) as response:
            names = [m["name"] for m in json.load(response)["models"]]
    except OSError:
        return False
    return any(n.split(":")[0] == MODEL for n in names)


# TC-16 (AC-14): with the real model, with and without the task prefixes
@pytest.mark.docker
@pytest.mark.ollama
def test_the_eval_with_the_real_model(engine: Engine) -> None:
    if not _ollama_has_the_model():
        pytest.skip(f"Ollama with {MODEL} is not reachable at {OLLAMA}")
    results = {
        label: run_eval(
            engine,
            label=label,
            doc_prefix=doc,
            query_prefix=query,
            client=None,
            url=OLLAMA,
        )
        for label, doc, query in (
            ("real model, prefixes search_document/search_query",
             "search_document: ", "search_query: "),
            ("real model, no prefixes", "", ""),
        )
    }  # fmt: skip
    for scores in results.values():
        assert all(0.0 <= v <= 1.0 for v in scores.values())  # no threshold
