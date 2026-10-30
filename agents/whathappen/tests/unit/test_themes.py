"""Theme counting and ranking (TC-6, TC-7, TC-8; AC-4, AC-5)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from whathappen.domain.articles import Article
from whathappen.domain.baseline import Baseline, BaselineEntry
from whathappen.domain.themes import RankedTheme, count_themes, rank_themes

T0 = datetime(2026, 10, 30, 0, 7, tzinfo=UTC)


def warm(articles: int = 1000, hours: int = 3, **themes: int) -> Baseline:
    return Baseline(
        entries=[
            BaselineEntry(at=T0 + timedelta(hours=i), articles=articles, themes=themes)
            for i in range(hours)
        ]
    )


def rank(
    counts: dict[str, int],
    n: int,
    baseline: Baseline,
    *,
    skip: tuple[str, ...] = (),
    min_count: int = 5,
    max_themes: int = 8,
    min_entries: int = 3,
) -> list[RankedTheme]:
    return rank_themes(
        counts,
        n,
        baseline,
        skip_prefixes=skip,
        min_count=min_count,
        max_themes=max_themes,
        min_entries=min_entries,
    )


def test_count_themes_counts_each_theme_once_per_article(
    make_article: Callable[..., Article],
) -> None:
    articles = [
        make_article(1, themes=["A", "A", "B"]),  # duplicate inside one article
        make_article(2, themes=["A"]),
        make_article(3, themes=[]),  # no themes: adds nothing
    ]
    assert count_themes(articles) == {"A": 2, "B": 1}


def test_tc6_rising_theme_ranks_above_a_big_steady_one() -> None:
    baseline = warm(1000, A=10, B=60)
    ranked = rank({"A": 40, "B": 60}, 1000, baseline)
    assert [r.code for r in ranked] == ["A", "B"]
    assert ranked[0].rise == pytest.approx(4.0)
    assert ranked[1].rise == pytest.approx(1.0)
    assert [r.count for r in ranked] == [40, 60]


def test_tc7_skip_prefixes_min_count_and_max_themes() -> None:
    baseline = warm(1000, A=10)
    counts = {"WB_1_X": 90, "A": 40, "TINY": 4, "C": 30, "D": 20, "E": 10}
    ranked = rank(counts, 1000, baseline, skip=("WB_",), min_count=5, max_themes=2)
    codes = [r.code for r in ranked]
    assert "WB_1_X" not in codes  # skipped
    assert "TINY" not in codes  # under the minimum
    assert len(ranked) == 2  # cut to the maximum


def test_tc7_a_theme_never_seen_before_gets_its_count_as_rise() -> None:
    ranked = rank({"NEW": 12}, 1000, warm(1000, OTHER=50))
    assert ranked[0].rise == pytest.approx(12.0)  # expected floored at 1


def test_tc7_a_window_twice_the_usual_size_does_not_double_every_rise() -> None:
    baseline = warm(1000, A=10)  # usual share 1 %
    ranked = rank({"A": 20}, 2000, baseline)  # 1 % of 2000 is what it usually is
    assert ranked[0].rise == pytest.approx(1.0)


def test_equal_rise_is_ordered_by_count_then_code() -> None:
    baseline = warm(1000, X=10, Y=20, Z=20)
    ranked = rank({"X": 10, "Y": 20, "Z": 20}, 1000, baseline)
    assert [r.code for r in ranked] == ["Y", "Z", "X"]  # rise 1.0 each; count; code


def test_tc8_cold_start_ranks_by_plain_count_without_a_rise() -> None:
    baseline = warm(1000, hours=2, A=500)  # only 2 entries: cold
    ranked = rank({"A": 30, "B": 50, "C": 5}, 1000, baseline)
    assert [r.code for r in ranked] == ["B", "A", "C"]
    assert all(r.rise is None for r in ranked)


def test_tc8_empty_baseline_is_cold() -> None:
    ranked = rank({"A": 30}, 1000, Baseline())
    assert ranked[0].rise is None


def test_a_zero_article_baseline_is_treated_as_cold() -> None:
    ranked = rank({"A": 30}, 1000, warm(0, hours=3))
    assert ranked[0].rise is None
