"""TC-2, TC-4 (fixture half), TC-5: the frozen hard-queries file and its builder.

`search_eval_hard_queries.json` is made from the two frozen M3f files by
`make eval-search-build-hard` (no network, no model). hybrid-eval-set, ADR-0039.
"""

import json
import socket
from pathlib import Path
from typing import Any

import build_search_eval_hard as wrapper
import pytest
import search_eval_build as build

FIXTURES = Path(__file__).resolve().parents[3] / "packages/core/tests/fixtures"
HARD = FIXTURES / "search_eval_hard_queries.json"


@pytest.fixture(scope="module")
def corpus() -> list[dict[str, Any]]:
    data = json.loads((FIXTURES / "search_eval_corpus.json").read_text())
    assert isinstance(data, list)
    return data


@pytest.fixture(scope="module")
def rows() -> list[dict[str, Any]]:
    data = json.loads(HARD.read_text())
    assert isinstance(data, dict) and isinstance(data["queries"], list)
    return data["queries"]


def test_the_frozen_hard_queries_pass_the_checker(
    corpus: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> None:  # TC-2, TC-4
    build.check_hard_fixture(corpus, rows)


def test_both_kinds_are_present_and_entity_queries_are_names(
    rows: list[dict[str, Any]],
) -> None:  # TC-2
    kinds = {r["kind"] for r in rows}
    assert kinds == {"entity", "lowoverlap"}
    for r in rows:
        if r["kind"] == "entity":
            assert 2 <= len(r["query"].split()) <= 3 * 2  # up to 3 names (hyphens)
            assert r["ignore"] == []
        else:
            assert r["expected"], r["query"]  # graded, never an empty low-overlap row


def test_the_builder_is_offline_and_repeatable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # TC-5
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("the hard builder must not open a socket")

    monkeypatch.setattr(socket, "socket", no_network)
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert wrapper.main(["--out", str(first)]) == 0
    assert wrapper.main(["--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes() == HARD.read_bytes()  # the committed file is its output
