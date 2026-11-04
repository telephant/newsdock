"""TC-1, TC-4, TC-5 (fixture half): the frozen search eval fixture obeys the rules.

The two files are built once by `make eval-search-build` from real GDELT slots (M3f,
ADR-0039) and live with the other real GDELT fixtures (DR-10).
"""

import json
from pathlib import Path
from typing import Any

import pytest
import search_eval_build as build

FIXTURES = Path(__file__).resolve().parents[3] / "packages/core/tests/fixtures"


@pytest.fixture(scope="module")
def corpus() -> list[dict[str, Any]]:
    data = json.loads((FIXTURES / "search_eval_corpus.json").read_text())
    assert isinstance(data, list)
    return data


@pytest.fixture(scope="module")
def queries() -> list[dict[str, Any]]:
    data = json.loads((FIXTURES / "search_eval_queries.json").read_text())
    assert isinstance(data, dict) and isinstance(data["queries"], list)
    return data["queries"]


def test_the_frozen_fixture_passes_the_builders_rules(
    corpus: list[dict[str, Any]], queries: list[dict[str, Any]]
) -> None:  # TC-1, TC-4, TC-5
    build.check_fixture(corpus, queries)  # unique ids, 2+ story keys, no copies...


def test_the_fixture_is_big_enough_to_discriminate_and_has_both_kinds(
    corpus: list[dict[str, Any]], queries: list[dict[str, Any]]
) -> None:
    ids = {c["id"] for c in corpus}
    members = {m for q in queries for m in q["members"]}
    assert {q["kind"] for q in queries} == set(build.KINDS)
    assert len(queries) >= 100  # measured at build time: 150
    assert len(ids - members) > len(members)  # many more distractors than relevant


def test_no_seed_is_used_by_two_clusters(queries: list[dict[str, Any]]) -> None:
    pairs = {(q["seed"], q["cluster"]) for q in queries}
    assert len({seed for seed, _ in pairs}) == len(pairs)
    texts = [(q["query"], q["kind"]) for q in queries]
    assert len(set(texts)) == len(texts)  # no duplicated query
