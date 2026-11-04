"""TC-7, TC-9, TC-12 and the dataset loaders: the pure parts of the eval harness."""

import pytest
import search_eval_harness as h


# --- datasets ------------------------------------------------------------------------
def test_the_easy_dataset_keeps_its_shape_and_has_no_seeds() -> None:
    easy = h.load_dataset("easy")
    assert len(easy.corpus) == 40 and len(easy.queries) == 12
    assert all(q["seed"] is None for q in easy.queries)


def test_the_events_dataset_loads_from_the_frozen_fixture() -> None:
    events = h.load_dataset("events")
    ids = {c["id"] for c in events.corpus}
    assert len(events.queries) >= 100
    for q in events.queries:
        assert q["seed"] in ids and set(q["expected"]) <= ids
        assert q["seed"] not in q["expected"]


def test_an_unknown_dataset_is_an_error() -> None:
    with pytest.raises(ValueError):
        h.load_dataset("nope")


# --- TC-7: leave-one-out -------------------------------------------------------------
def test_the_seed_is_removed_before_scoring_and_the_list_is_cut_to_k() -> None:
    got = h.without_seed(["s", "a", "b", "c", "d", "e", "f"], "s", k=5)
    assert got == ["a", "b", "c", "d", "e"]
    assert h.without_seed(["a", "b"], None, k=5) == ["a", "b"]  # no seed: unchanged


def test_scoring_a_run_never_counts_the_seed() -> None:
    run = h.QueryRun(
        kind="paraphrase",
        expected=["b"],
        found={"vector": h.without_seed(["s", "b"], "s", k=5)},
    )
    assert h.recall_at_k(run.expected, run.found["vector"]) == 1.0
    assert h.reciprocal_rank(run.expected, run.found["vector"]) == 1.0  # rank 1, not 2


def test_metrics_average_over_queries_and_split_by_kind() -> None:
    runs = [
        h.QueryRun("a", ["x"], {"vector": ["x"]}),
        h.QueryRun("a", ["x"], {"vector": ["y"]}),
        h.QueryRun("b", ["x"], {"vector": ["y", "x"]}),
    ]
    assert h.metrics(runs, "vector") == pytest.approx((2 / 3, (1 + 0 + 0.5) / 3))
    by_kind = h.metrics_by_kind(runs, "vector")
    assert by_kind["a"] == (0.5, 0.5) and by_kind["b"] == (1.0, 0.5)


# --- TC-9: hybrid noise -----------------------------------------------------------
def test_noise_counts_relevant_vector_hits_that_hybrid_dropped() -> None:
    runs = [
        h.QueryRun(
            "k", ["a", "b"],
            {"vector": ["a", "b", "x"], "hybrid": ["k1", "k2", "a"],
             "fulltext": ["k1", "b"]},
        ),  # b is relevant in vector's top 5 but missing from hybrid's
        h.QueryRun("k", ["a"], {"vector": ["a"], "hybrid": ["a"], "fulltext": ["z"]}),
    ]  # fmt: skip
    noise = h.noise(runs)
    assert noise.relevant_vector_hits == 3
    assert noise.dropped_by_hybrid_vs_vector == 1
    assert noise.relevant_fulltext_hits == 1
    assert noise.dropped_by_hybrid_vs_fulltext == 1  # b again


# --- TC-12: paired bootstrap ------------------------------------------------------
def test_paired_bootstrap_is_deterministic_for_a_fixed_seed() -> None:
    a, b = [1.0, 0.5, 0.0, 1.0, 0.5], [0.5, 0.5, 0.0, 0.5, 0.0]
    assert h.paired_bootstrap(a, b, n=200, seed=1) == h.paired_bootstrap(
        a, b, n=200, seed=1
    )


def test_the_interval_excludes_zero_for_clearly_different_scores() -> None:
    a, b = [1.0] * 30, [0.0] * 30
    low, high = h.paired_bootstrap(a, b, n=200, seed=0)
    assert low > 0 and high > 0


def test_the_interval_includes_zero_for_identical_scores() -> None:
    same = [1.0, 0.5, 0.0, 0.25] * 5
    low, high = h.paired_bootstrap(same, list(same), n=200, seed=0)
    assert low <= 0 <= high


def test_clear_win_needs_the_interval_recall_and_every_kind() -> None:
    base = [h.QueryRun("p", ["x"], {"vector": ["y", "x"]}) for _ in range(30)] + [
        h.QueryRun("k", ["x"], {"vector": ["y", "x"]}) for _ in range(30)
    ]
    better = [h.QueryRun("p", ["x"], {"vector": ["x"]}) for _ in range(30)] + [
        h.QueryRun("k", ["x"], {"vector": ["x"]}) for _ in range(30)
    ]
    worse_in_one_kind = [
        h.QueryRun("p", ["x"], {"vector": ["x"]}) for _ in range(30)
    ] + [h.QueryRun("k", ["x"], {"vector": ["y", "z", "x"]}) for _ in range(30)]
    assert h.clear_win(better, base, "vector") is True
    assert h.clear_win(base, base, "vector") is False
    assert h.clear_win(worse_in_one_kind, base, "vector") is False
