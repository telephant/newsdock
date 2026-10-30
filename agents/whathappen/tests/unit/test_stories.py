"""Story picker (TC-10; AC-6)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from whathappen.domain.articles import Article
from whathappen.domain.stories import pick_stories
from whathappen.domain.themes import RankedTheme

T0 = datetime(2026, 10, 30, 14, 0, tzinfo=UTC)


def theme(code: str, count: int = 10) -> RankedTheme:
    return RankedTheme(code, count, None)


def ids(articles: list[Article]) -> list[str]:
    return [a.article_id for a in articles]


def test_top_stories_by_source_count_then_newest_then_id(
    make_article: Callable[..., Article],
) -> None:
    arts = [
        make_article(1, themes=["A"], source_count=1, published_at=T0),
        make_article(2, themes=["A"], source_count=5, published_at=T0),
        make_article(3, themes=["A"], source_count=3, published_at=T0),
        make_article(4, themes=["A"], source_count=3, published_at=T0 + timedelta(1)),
        make_article(5, themes=["A"], source_count=3, published_at=T0 + timedelta(1)),
        make_article(6, themes=["A"], source_count=2, published_at=T0),
    ]
    [pick] = pick_stories([theme("A")], arts, per_theme=3, prompt_titles=5)
    # 5 sources first; the three-source ties go newest first, then by article_id
    assert ids(pick.shown) == ["id2", "id4", "id5"]
    assert ids(pick.prompt_articles) == ["id2", "id4", "id5", "id3", "id6"]


def test_a_story_with_two_ranked_themes_stays_under_the_higher_ranked_one(
    make_article: Callable[..., Article],
) -> None:
    arts = [
        make_article(1, themes=["A", "B"], source_count=9),  # both themes
        make_article(2, themes=["B"], source_count=4),
        make_article(3, themes=["B"], source_count=2),
    ]
    first, second = pick_stories(
        [theme("A"), theme("B")], arts, per_theme=2, prompt_titles=4
    )
    assert ids(first.shown) == ["id1"]
    assert ids(second.shown) == ["id2", "id3"]  # B takes the next best, not id1
    all_taken = ids(first.prompt_articles) + ids(second.prompt_articles)
    assert len(all_taken) == len(set(all_taken))  # no story twice


def test_prompt_articles_are_own_stories_up_to_the_limit_and_shown_are_the_first_k(
    make_article: Callable[..., Article],
) -> None:
    arts = [make_article(i, themes=["A"], source_count=20 - i) for i in range(1, 11)]
    [pick] = pick_stories([theme("A")], arts, per_theme=3, prompt_titles=8)
    assert len(pick.prompt_articles) == 8
    assert pick.shown == pick.prompt_articles[:3]


def test_a_theme_whose_stories_were_all_taken_comes_back_empty(
    make_article: Callable[..., Article],
) -> None:
    arts = [make_article(1, themes=["A", "B"])]
    first, second = pick_stories(
        [theme("A"), theme("B")], arts, per_theme=3, prompt_titles=8
    )
    assert ids(first.shown) == ["id1"]
    assert second.shown == [] and second.prompt_articles == []
    assert second.theme.code == "B"  # still listed, in rank order


def test_picks_keep_the_rank_order_and_the_window_count(
    make_article: Callable[..., Article],
) -> None:
    arts = [make_article(1, themes=["A"]), make_article(2, themes=["B"])]
    picks = pick_stories(
        [theme("B", 7), theme("A", 3)], arts, per_theme=3, prompt_titles=8
    )
    assert [(p.theme.code, p.theme.count) for p in picks] == [("B", 7), ("A", 3)]


def test_no_ranked_themes_gives_no_picks(
    make_article: Callable[..., Article],
) -> None:
    assert pick_stories([], [make_article(1, themes=["A"])], 3, 8) == []
