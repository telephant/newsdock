"""TC-1, TC-2 (AC-1, AC-2): scoring story groups by coverage and tone."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from whathappen.domain.articles import Article
from whathappen.domain.grouping import StoryGroup
from whathappen.domain.scoring import RANKING_COVERAGE, RANKING_TONE, score_groups

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def group_of(*members: Article) -> StoryGroup:
    return StoryGroup(tuple(members))


# --- TC-1: coverage x (1 + tone / divisor) ------------------------------------------
def test_scores_and_order_follow_sources_times_tone(
    make_article: Callable[..., Article],
) -> None:
    a = group_of(make_article(1, source_count=50, tone_neg=2.0))
    b = group_of(make_article(2, source_count=35, tone_neg=6.7))
    c = group_of(make_article(3, source_count=60, tone_neg=0.2))
    scored, ranking = score_groups([a, b, c], tone_divisor=10)
    assert [s.score for s in scored] == pytest.approx([61.2, 60.0, 58.45])
    assert [s.group for s in scored] == [c, a, b]
    assert [s.sources for s in scored] == [60, 50, 35]
    assert ranking == RANKING_TONE


def test_the_divisor_is_a_parameter(make_article: Callable[..., Article]) -> None:
    g = group_of(make_article(1, source_count=10, tone_neg=5.0))
    (scored,), _ = score_groups([g], tone_divisor=10)
    assert scored.score == pytest.approx(15.0)
    (scored,), _ = score_groups([g], tone_divisor=5)
    assert scored.score == pytest.approx(20.0)


@pytest.mark.parametrize("divisor", [0, -1, -0.5])
def test_a_non_positive_divisor_is_refused(
    make_article: Callable[..., Article], divisor: float
) -> None:
    with pytest.raises(ValueError, match="tone_divisor"):
        score_groups([group_of(make_article(1))], tone_divisor=divisor)


def test_a_group_sums_its_sources_and_takes_its_largest_tone(
    make_article: Callable[..., Article],
) -> None:
    g = group_of(
        make_article(1, source_count=30, tone_neg=3.0, domain="a.com"),
        make_article(2, source_count=20, tone_neg=9.0, domain="b.com"),
        make_article(3, source_count=1, tone_neg=None, domain="c.com"),
    )
    (scored,), _ = score_groups([g], tone_divisor=10)
    assert scored.sources == 51
    assert scored.tone_neg == 9.0
    assert scored.score == pytest.approx(51 * 1.9)


def test_ties_break_by_sources_then_newest_then_id(
    make_article: Callable[..., Article],
) -> None:
    # all three score 60.0
    more_sources = group_of(make_article(1, source_count=60, tone_neg=0.0))
    older = group_of(
        make_article(
            2, source_count=50, tone_neg=2.0, published_at=NOW - timedelta(hours=2)
        )
    )
    newer = group_of(make_article(3, source_count=50, tone_neg=2.0, published_at=NOW))
    scored, _ = score_groups([older, newer, more_sources], tone_divisor=10)
    assert [s.score for s in scored] == pytest.approx([60.0, 60.0, 60.0])
    assert [s.group for s in scored] == [more_sources, newer, older]


def test_identical_scores_fall_back_to_the_article_id(
    make_article: Callable[..., Article],
) -> None:
    first = group_of(make_article(1, source_count=5, tone_neg=1.0))
    second = group_of(make_article(2, source_count=5, tone_neg=1.0))
    scored, _ = score_groups([second, first], tone_divisor=10)
    assert [s.group for s in scored] == [first, second]


def test_an_empty_input_is_an_empty_ranking() -> None:
    assert score_groups([], tone_divisor=10) == ([], RANKING_COVERAGE)


# --- TC-2: no tone means coverage only -----------------------------------------------
def test_without_any_tone_the_score_is_the_source_total(
    make_article: Callable[..., Article],
) -> None:
    a = group_of(make_article(1, source_count=7))
    b = group_of(make_article(2, source_count=12))
    scored, ranking = score_groups([a, b], tone_divisor=10)
    assert ranking == RANKING_COVERAGE
    assert [s.score for s in scored] == [12.0, 7.0]
    assert [s.tone_neg for s in scored] == [None, None]


def test_a_platform_that_returns_only_nulls_is_coverage_only(
    make_article: Callable[..., Article],
) -> None:
    g = group_of(make_article(1, source_count=7, tone_neg=None))
    (scored,), ranking = score_groups([g], tone_divisor=10)
    assert ranking == RANKING_COVERAGE
    assert scored.score == 7.0


def test_one_non_null_tone_anywhere_switches_the_ranking_note(
    make_article: Callable[..., Article],
) -> None:
    with_tone = group_of(make_article(1, source_count=10, tone_neg=5.0))
    without = group_of(make_article(2, source_count=14))
    scored, ranking = score_groups([with_tone, without], tone_divisor=10)
    assert ranking == RANKING_TONE
    # the group without tone counts as 0, not as "unknown"
    by_id = {s.group.shown.article_id: s for s in scored}
    assert by_id[without.shown.article_id].score == 14.0
    assert by_id[with_tone.shown.article_id].score == pytest.approx(15.0)
    assert [s.group for s in scored] == [with_tone, without]
