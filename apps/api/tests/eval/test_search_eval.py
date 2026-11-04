"""TC-15/16 (semantic-search AC-14) and TC-6, TC-8, TC-10, TC-11, TC-13 (M3f).

Two datasets (`search_eval_harness`): `easy`, the original 40 hand-written titles,
and `events`, real titles whose relevance comes from GDELT events confirmed by a local
model (frozen by `make eval-search-build`, ADR-0039). Each run loads a dataset into a
throwaway Postgres and runs every query through the substring search `search_articles`
uses, the full-text leg, the vector leg and the hybrid fusion, with the query's seed
removed from the results (leave-one-out). The numbers are printed; no threshold is
asserted (measure first). The fake-embedder tests check the harness; the real-model
tests (`make eval-search`, `make eval-search-sweep`) are read by a person.
"""

import json
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import search_eval_harness as h
from alembic import command
from alembic.config import Config
from newsdock_api.config import Settings
from newsdock_db.engine import make_engine
from newsdock_embedding.testing import FakeOllama
from sqlalchemy import Engine

ROOT = Path(__file__).resolve().parents[4]
OLLAMA = "http://127.0.0.1:11434"
FAKE_URL = "http://ollama.test:11434"


def test_reciprocal_rank_is_one_over_the_first_hit() -> None:
    assert h.reciprocal_rank(["a", "b"], ["a", "x"]) == 1.0
    assert h.reciprocal_rank(["a", "b"], ["x", "b", "a"]) == 0.5
    assert h.reciprocal_rank(["a"], ["x", "y"]) == 0.0
    assert h.reciprocal_rank(["a"], []) == 0.0


def test_recall_at_k_counts_expected_ids_in_the_top_k() -> None:
    assert h.recall_at_k(["a", "b"], ["a", "x", "b"]) == 1.0
    assert h.recall_at_k(["a", "b"], ["a", "x", "y"]) == 0.5
    assert h.recall_at_k(["a", "b"], ["x", "y", "z"]) == 0.0
    assert h.recall_at_k(["a"], ["x", "y", "z", "q", "r", "a"], k=5) == 0.0  # sixth
    assert h.recall_at_k(["a", "a"], ["a"]) == 1.0  # duplicates in the label count once


def test_recall_at_k_needs_something_to_find() -> None:
    with pytest.raises(ValueError):
        h.recall_at_k([], ["a"])


def test_the_labelled_queries_point_at_articles_in_the_corpus() -> None:
    for name in ("easy", "events", "events-hard"):
        dataset = h.load_dataset(name)
        corpus = {c["id"] for c in dataset.corpus}
        assert len(corpus) == len(dataset.corpus)
        for q in dataset.queries:
            assert q["expected"] and set(q["expected"]) <= corpus, q["query"]
            assert set(q["ignore"]) <= corpus, q["query"]
    assert len(h.load_dataset("easy").corpus) == 40
    assert len(h.load_dataset("easy").queries) == 12


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
    dataset: str,
    doc_prefix: str,
    query_prefix: str,
    client: httpx.Client | None,
    url: str,
) -> dict[str, float]:
    """Embed and load a dataset, run every query through the four methods, print."""
    data = h.load_dataset(dataset)
    settings = Settings()
    h.load_corpus(engine, data, doc_prefix=doc_prefix, client=client, url=url)
    embedder = h.make_embedder(query_prefix=query_prefix, client=client, url=url)
    runs = h.run_queries(
        engine, data, embedder, rrf_k=settings.semantic_rrf_k,
        candidates=settings.semantic_candidates,
    )  # fmt: skip
    return h.print_report(
        label, data, runs, rrf_k=settings.semantic_rrf_k,
        candidates=settings.semantic_candidates,
    )  # fmt: skip


# TC-15 (semantic-search AC-14): the harness runs, with a fake embedder
@pytest.mark.docker
def test_the_eval_prints_recall_for_keyword_vector_and_hybrid(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeOllama()
    with httpx.Client(transport=fake.transport()) as client:
        scores = run_eval(
            engine, label="fake embedder", dataset="easy",
            doc_prefix="search_document: ", query_prefix="search_query: ",
            client=client, url=FAKE_URL,
        )  # fmt: skip
    out = capsys.readouterr().out
    for method in ("keyword", "vector", "hybrid"):
        assert h.LABELS[method] in out
    assert set(scores) == set(h.METHODS)
    assert all(0.0 <= v <= 1.0 for v in scores.values())
    # no threshold on quality (AC-14), but the baselines must have found something
    assert scores["keyword"] > 0.0 and scores["fulltext"] > 0.0


# TC-6 (AC-5) and TC-10 (AC-8): the events dataset, by kind, with the noise line
@pytest.mark.docker
def test_the_events_eval_prints_overall_by_kind_and_noise(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeOllama()
    with httpx.Client(transport=fake.transport()) as client:
        scores = run_eval(
            engine, label="fake embedder", dataset="events",
            doc_prefix="search_document: ", query_prefix="search_query: ",
            client=client, url=FAKE_URL,
        )  # fmt: skip
    out = capsys.readouterr().out
    assert "dataset=events" in out and "by kind of query" in out
    for method in h.METHODS:
        assert h.LABELS[method] in out
    for kind in ("paraphrase", "keywords"):
        assert kind in out
    assert "hybrid noise" in out
    assert set(scores) == set(h.METHODS)


# TC-7 (hybrid-eval-set AC-7): events-hard prints entity and lowoverlap by kind
@pytest.mark.docker
def test_the_events_hard_eval_prints_entity_and_lowoverlap_kinds(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeOllama()
    with httpx.Client(transport=fake.transport()) as client:
        scores = run_eval(
            engine, label="fake embedder", dataset="events-hard",
            doc_prefix="search_document: ", query_prefix="search_query: ",
            client=client, url=FAKE_URL,
        )  # fmt: skip
    out = capsys.readouterr().out
    assert "dataset=events-hard" in out and "by kind of query" in out
    for kind in ("entity", "lowoverlap"):
        assert kind in out
    assert "hybrid noise" in out
    assert set(scores) == set(h.METHODS)


# TC-11 (AC-9): the same fixture and settings give the same numbers
@pytest.mark.docker
def test_two_runs_print_identical_numbers(engine: Engine) -> None:
    fake = FakeOllama()
    results = []
    for _ in range(2):
        with httpx.Client(transport=fake.transport()) as client:
            results.append(
                run_eval(
                    engine,
                    label="repeat",
                    dataset="events",
                    doc_prefix="search_document: ",
                    query_prefix="search_query: ",
                    client=client,
                    url=FAKE_URL,
                )  # fmt: skip
            )
    assert results[0] == results[1]


# TC-8 (AC-6, and hybrid-eval-set AC-9): the sweep prints one row per combination
@pytest.mark.docker
@pytest.mark.parametrize("dataset", ["events", "events-hard"])
def test_the_sweep_has_one_row_per_combination(
    engine: Engine, capsys: pytest.CaptureFixture[str], dataset: str
) -> None:
    fake = FakeOllama()
    data = h.load_dataset(dataset)
    with httpx.Client(transport=fake.transport()) as client:
        rows = h.sweep(engine, data, client=client, url=FAKE_URL)
    assert len(rows) == 2 * len(h.GRID_RRF_K) * len(h.GRID_CANDIDATES) == 24
    assert {(r.prefix, r.rrf_k, r.candidates) for r in rows} == {
        (p, k, c)
        for p in (True, False)
        for k in h.GRID_RRF_K
        for c in h.GRID_CANDIDATES
    }
    h.print_sweep(rows)
    out = capsys.readouterr().out
    assert out.count("\n  on ") + out.count("\n  off") == 24
    assert "clear wins over the defaults" in out


def _ollama_has_the_model() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=3) as response:
            names = [m["name"] for m in json.load(response)["models"]]
    except OSError:
        return False
    return any(n.split(":")[0] == h.MODEL for n in names)


# TC-16 (AC-14) and TC-13 (AC-7): the real model, both datasets, with and without
# the task prefixes; read by a person
@pytest.mark.docker
@pytest.mark.ollama
def test_the_eval_with_the_real_model(engine: Engine) -> None:
    if not _ollama_has_the_model():
        pytest.skip(f"Ollama with {h.MODEL} is not reachable at {OLLAMA}")
    for dataset in ("easy", "events", "events-hard"):
        for label, prefixed in (("prefixes search_document/search_query", True),
                                ("no prefixes", False)):  # fmt: skip
            doc, query = h.PREFIXES[prefixed]
            scores = run_eval(
                engine, label=f"real model, {label}", dataset=dataset,
                doc_prefix=doc, query_prefix=query, client=None, url=OLLAMA,
            )  # fmt: skip
            assert all(0.0 <= v <= 1.0 for v in scores.values())  # no threshold


# the sweep with the real model (`make eval-search-sweep`); read by a person
@pytest.mark.docker
@pytest.mark.ollama
def test_the_sweep_with_the_real_model(engine: Engine) -> None:
    if not _ollama_has_the_model():
        pytest.skip(f"Ollama with {h.MODEL} is not reachable at {OLLAMA}")
    for dataset in ("events", "events-hard"):
        print(f"\n#### sweep on dataset {dataset}")
        rows = h.sweep(engine, h.load_dataset(dataset), client=None, url=OLLAMA)
        h.print_sweep(rows)
        assert len(rows) == 24
