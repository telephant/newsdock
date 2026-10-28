"""Bounded skip list and capped backoff (spec D-3, design-detail §2)."""

import pytest
from newsdock_embedder.domain.selection import Backoff, SkipList


def test_a_key_is_excluded_after_max_failures() -> None:
    skip = SkipList(max_failures=3, max_entries=100)
    skip.fail("a")
    skip.fail("a")
    assert skip.excluded() == frozenset()
    skip.fail("a")
    assert skip.excluded() == frozenset({"a"})


def test_failures_of_other_keys_do_not_add_up() -> None:
    skip = SkipList(max_failures=2, max_entries=100)
    skip.fail("a")
    skip.fail("b")
    assert skip.excluded() == frozenset()


def test_forget_clears_a_key() -> None:
    skip = SkipList(max_failures=1, max_entries=100)
    skip.fail("a")
    assert "a" in skip.excluded()
    skip.forget("a")
    assert skip.excluded() == frozenset()


def test_the_table_is_bounded() -> None:
    skip = SkipList(max_failures=1, max_entries=10)
    for i in range(50):
        skip.fail(f"k{i}")
    assert len(skip.excluded()) <= 10


def test_backoff_doubles_up_to_the_cap_and_resets() -> None:
    backoff = Backoff(base=5.0, cap=60.0)
    assert [backoff.next() for _ in range(6)] == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0]
    backoff.reset()
    assert backoff.next() == 5.0


@pytest.mark.parametrize("base,cap", [(0.0, 10.0), (5.0, 1.0)])
def test_backoff_rejects_nonsense(base: float, cap: float) -> None:
    with pytest.raises(ValueError):
        Backoff(base=base, cap=cap)
