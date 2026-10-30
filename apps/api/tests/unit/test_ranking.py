"""TC-8 (AC-8): reciprocal-rank fusion of ranked id lists, pure."""

from datetime import UTC, datetime, timedelta

import pytest
from newsdock_api.domain.ranking import Fused, Ranked, fuse

T0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def hit(article_id: str, minutes_ago: int = 0) -> Ranked:
    return Ranked(article_id, T0 - timedelta(minutes=minutes_ago))


def ids(fused: list[Fused]) -> list[str]:
    return [f.id for f in fused]


def test_an_id_in_both_legs_outranks_ids_in_one() -> None:
    fused = fuse(
        {
            "vector": [hit("B"), hit("A")],
            "keyword": [hit("C"), hit("A")],
        },
        k=60,
    )
    assert ids(fused)[0] == "A"
    assert set(ids(fused)) == {"A", "B", "C"}


def test_score_is_the_sum_of_one_over_k_plus_rank() -> None:
    fused = fuse({"vector": [hit("X"), hit("A")], "keyword": [hit("A")]}, k=60)
    by_id = {f.id: f for f in fused}
    assert by_id["A"].score == pytest.approx(1 / 62 + 1 / 61)
    assert by_id["X"].score == pytest.approx(1 / 61)


def test_matched_by_lists_the_legs_in_the_given_order() -> None:
    fused = fuse(
        {"vector": [hit("A"), hit("B")], "keyword": [hit("A"), hit("C")]}, k=60
    )
    by_id = {f.id: f for f in fused}
    assert by_id["A"].matched_by == ("vector", "keyword")
    assert by_id["B"].matched_by == ("vector",)
    assert by_id["C"].matched_by == ("keyword",)


def test_a_better_rank_in_a_single_leg_wins() -> None:
    fused = fuse({"vector": [hit("first"), hit("second"), hit("third")]}, k=60)
    assert ids(fused) == ["first", "second", "third"]


def test_ties_break_by_newest_then_by_id() -> None:
    # Same rank in two different single-id legs gives equal scores.
    fused = fuse(
        {
            "vector": [hit("old", minutes_ago=30)],
            "keyword": [hit("new", minutes_ago=5)],
        },
        k=60,
    )
    assert ids(fused) == ["new", "old"]

    same_time = fuse({"vector": [hit("b")], "keyword": [hit("a")]}, k=60)
    assert ids(same_time) == ["a", "b"]


def test_an_empty_leg_leaves_the_other_order_unchanged() -> None:
    fused = fuse({"vector": [], "keyword": [hit("A"), hit("B"), hit("C")]}, k=60)
    assert ids(fused) == ["A", "B", "C"]
    assert all(f.matched_by == ("keyword",) for f in fused)


def test_no_legs_or_only_empty_legs_give_nothing() -> None:
    assert fuse({}, k=60) == []
    assert fuse({"vector": [], "keyword": []}, k=60) == []


def test_a_repeated_id_in_one_leg_counts_once_at_its_first_rank() -> None:
    fused = fuse({"vector": [hit("A"), hit("B"), hit("A")]}, k=60)
    assert ids(fused) == ["A", "B"]
    assert fused[0].score == pytest.approx(1 / 61)


def test_k_sets_how_much_the_top_rank_is_worth() -> None:
    # A is first in one leg only; B is third in both. B wins only when k > 1:
    # 2 / (k + 3) > 1 / (k + 1)  <=>  k > 1  (a tie at k = 1).
    legs = {
        "vector": [hit("A"), hit("x"), hit("B")],
        "keyword": [hit("y"), hit("z"), hit("B")],
    }
    assert ids(fuse(legs, k=60))[0] == "B"
    at_k1 = {f.id: f.score for f in fuse(legs, k=1)}
    assert at_k1["A"] == pytest.approx(at_k1["B"])  # the tie at k = 1


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_positive(k: int) -> None:
    with pytest.raises(ValueError):
        fuse({"vector": [hit("A")]}, k=k)
