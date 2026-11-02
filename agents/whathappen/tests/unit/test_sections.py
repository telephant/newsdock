"""TC-7 (selection), TC-8, TC-9 (label map): selection and sections (AC-6, AC-7)."""

from collections.abc import Callable, Sequence

import pytest

from whathappen.domain.articles import Article
from whathappen.domain.grouping import StoryGroup
from whathappen.domain.scoring import ScoredGroup, score_groups
from whathappen.domain.sections import (
    DEFAULT_SECTIONS,
    OTHER,
    SelectParams,
    label_for,
    parse_section_labels,
    select,
)

LABELS = (
    ("Politics & Government", ("ELECTION", "LEGISLATION", "GOV_")),
    ("Conflict & Security", ("ARMEDCONFLICT", "MILITARY")),
)


def params(**over: object) -> SelectParams:
    base: dict[str, object] = {
        "top_stories": 5,
        "max_sections": 6,
        "groups_per_section": 4,
        "min_group_sources": 2,
        "section_min_hits": 1,
        "labels": LABELS,
    }
    base.update(over)
    return SelectParams(**base)  # type: ignore[arg-type]


def group(
    make_article: Callable[..., Article], n: int, sources: int, *themes: str
) -> StoryGroup:
    return StoryGroup(
        (
            make_article(
                n, source_count=sources, themes=list(themes), domain=f"d{n}.com"
            ),
        )
    )


def ranked(groups: Sequence[StoryGroup]) -> list[ScoredGroup]:
    scored, _ = score_groups(groups, tone_divisor=10)
    return scored


def titles(items: Sequence[ScoredGroup]) -> list[str]:
    return [s.group.shown.article_id for s in items]


# --- TC-8: the label of one group (a vote over its articles' themes) ------------------
def test_the_label_with_the_most_theme_hits_wins(
    make_article: Callable[..., Article],
) -> None:
    g = StoryGroup(
        (
            make_article(1, themes=["ELECTION", "ARMEDCONFLICT"], domain="a.com"),
            make_article(2, themes=["ARMEDCONFLICT", "MILITARY"], domain="b.com"),
        )
    )  # Politics 1 hit, Conflict 3 hits (the second label is ahead)
    assert label_for(g, LABELS, min_hits=1) == "Conflict & Security"


def test_a_tie_goes_to_the_label_listed_first(
    make_article: Callable[..., Article],
) -> None:
    g = group(make_article, 1, 5, "ARMEDCONFLICT", "ELECTION")
    assert label_for(g, LABELS, min_hits=1) == "Politics & Government"


def test_no_hit_is_other(make_article: Callable[..., Article]) -> None:
    assert label_for(group(make_article, 1, 5, "EDUCATION"), LABELS, 1) == OTHER
    assert label_for(group(make_article, 2, 5), LABELS, 1) == OTHER


def test_a_label_needs_the_minimum_number_of_hits(
    make_article: Callable[..., Article],
) -> None:
    one = group(make_article, 1, 5, "ELECTION")
    two = group(make_article, 2, 5, "ELECTION", "LEGISLATION")
    assert label_for(one, LABELS, min_hits=1) == "Politics & Government"
    assert label_for(one, LABELS, min_hits=2) == OTHER
    assert label_for(two, LABELS, min_hits=2) == "Politics & Government"


def test_a_theme_counts_once_per_label_even_if_two_prefixes_match(
    make_article: Callable[..., Article],
) -> None:
    labels = (("A", ("ELECTION", "ELECTION_FRAUD")), ("B", ("MILITARY",)))
    g = group(make_article, 1, 5, "ELECTION_FRAUD", "MILITARY")
    # A would win 2 to 1 if both prefixes counted; one theme counts once: a tie
    assert label_for(g, labels, 1) == "A"
    two_b = group(make_article, 2, 5, "ELECTION_FRAUD", "MILITARY", "MILITARY_X")
    assert label_for(two_b, labels, 1) == "B"


def test_prefixes_match_the_start_of_a_theme(
    make_article: Callable[..., Article],
) -> None:
    assert label_for(group(make_article, 1, 5, "GOV_LOCALGOV"), LABELS, 1) == (
        "Politics & Government"
    )
    assert label_for(group(make_article, 2, 5, "XGOV_LOCALGOV"), LABELS, 1) == OTHER


# --- TC-7: who is listed, and where ---------------------------------------------------
def test_the_top_block_is_the_best_five_in_order_and_not_repeated(
    make_article: Callable[..., Article],
) -> None:
    groups = [group(make_article, i, 10 + i, "ELECTION") for i in range(1, 9)]  # 11..18
    selection = select(ranked(groups), params())
    assert titles(selection.top) == ["id8", "id7", "id6", "id5", "id4"]
    listed_in_sections = [t for s in selection.sections for t in titles(s.groups)]
    assert listed_in_sections == ["id3", "id2", "id1"]
    assert not set(titles(selection.top)) & set(listed_in_sections)


def test_fewer_qualifying_groups_than_the_top_size_gives_a_shorter_block(
    make_article: Callable[..., Article],
) -> None:
    groups = [group(make_article, i, 5) for i in range(1, 4)]
    selection = select(ranked(groups), params())
    assert len(selection.top) == 3
    assert selection.sections == ()


def test_groups_below_the_minimum_sources_are_dropped(
    make_article: Callable[..., Article],
) -> None:
    solo = group(make_article, 1, 1, "ELECTION")
    pair = StoryGroup(
        (
            make_article(2, source_count=1, domain="a.com"),
            make_article(3, source_count=1, domain="b.com"),
        )
    )  # two outlets: 2 sources together
    selection = select(ranked([solo, pair]), params())
    assert titles(selection.top) == [pair.shown.article_id]
    assert select(ranked([solo]), params()).top == ()
    assert select(ranked([solo]), params(min_group_sources=1)).top != ()


def test_sections_are_ordered_by_their_best_score_and_empty_ones_do_not_exist(
    make_article: Callable[..., Article],
) -> None:
    groups = [
        group(make_article, 1, 30, "MILITARY"),
        group(make_article, 2, 28, "ELECTION"),
        group(make_article, 3, 20, "ELECTION"),
        group(make_article, 4, 19, "NOTHING"),
        group(make_article, 5, 12, "MILITARY"),
        group(make_article, 6, 11, "MILITARY"),
    ]
    selection = select(ranked(groups), params(top_stories=1))
    assert [s.label for s in selection.sections] == [
        "Politics & Government",
        OTHER,
        "Conflict & Security",
    ]
    assert titles(selection.sections[0].groups) == ["id2", "id3"]
    assert all(s.groups for s in selection.sections)


def test_the_caps_hold(make_article: Callable[..., Article]) -> None:
    groups = (
        [group(make_article, i, 90 - i, "ELECTION") for i in range(1, 6)]
        + [group(make_article, i, 60 - i, "MILITARY") for i in range(6, 9)]
        + [group(make_article, i, 30 - i, "UNMATCHED") for i in range(9, 12)]
    )
    selection = select(
        ranked(groups), params(top_stories=2, max_sections=2, groups_per_section=2)
    )
    assert len(selection.top) == 2
    assert len(selection.sections) == 2
    assert all(len(s.groups) <= 2 for s in selection.sections)
    # the third section (Other, lowest score) is cut; no group is listed twice
    assert OTHER not in [s.label for s in selection.sections]
    everything = titles(selection.top) + [
        t for s in selection.sections for t in titles(s.groups)
    ]
    assert len(everything) == len(set(everything))


def test_an_empty_input_selects_nothing() -> None:
    selection = select([], params())
    assert selection.top == () and selection.sections == ()


# --- TC-9: the label map --------------------
def test_parse_keeps_the_order_of_labels_and_prefixes() -> None:
    raw = '{"B label": ["X_", "Y"], "A label": ["Z"]}'
    assert parse_section_labels(raw) == (("B label", ("X_", "Y")), ("A label", ("Z",)))


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '"text"',
        '{"A": "ELECTION"}',  # prefixes must be a list
        '{"A": [""]}',  # empty prefix
        '{"A": [5]}',
        '{"": ["X"]}',  # empty label
        '{"Other": ["X"]}',  # reserved
    ],
)
def test_parse_rejects_bad_maps_with_a_clear_message(raw: str) -> None:
    with pytest.raises(ValueError, match="section_labels"):
        parse_section_labels(raw)


def test_an_empty_map_means_everything_is_other() -> None:
    assert parse_section_labels("{}") == ()


def test_the_default_map_is_specific_and_unambiguous() -> None:
    labels = [name for name, _ in DEFAULT_SECTIONS]
    assert labels == [
        "Conflict & Security",
        "Politics & Government",
        "Business & Markets",
        "Crime & Courts",
        "Health",
        "Disasters & Accidents",
    ]
    prefixes = [p for _, ps in DEFAULT_SECTIONS for p in ps]
    assert len(prefixes) == len(set(prefixes))  # a prefix belongs to one label
    # generic codes that tag unrelated stories on real data are left out on purpose
    noisy = {"EDUCATION", "MANMADE_DISASTER_IMPLIED", "SECURITY_SERVICES", "KILL"}
    assert not noisy & set(prefixes)
