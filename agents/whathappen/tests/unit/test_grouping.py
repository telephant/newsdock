"""TC-3, TC-4, TC-5 (AC-3, AC-4, AC-5): the lexical story grouper on real pairs."""

import json
import random
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from whathappen.domain.articles import Article
from whathappen.domain.grouping import LexicalGrouper, StoryGrouper
from whathappen.domain.titles import MatchParams, matches, title_tokens

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WINDOW = timedelta(hours=48)
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


def grouper(window: timedelta = WINDOW) -> LexicalGrouper:
    return LexicalGrouper(MatchParams(), window)


def article(raw: dict[str, Any]) -> Article:
    return Article.from_mcp(raw)


@pytest.fixture(scope="module")
def pairs() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "story_pairs.json").read_text())
    return data


def ids(group: Any) -> set[str]:
    return {m.article_id for m in group.members}


# --- the port ------------------------------------------------------------------------
def test_the_lexical_grouper_is_a_story_grouper() -> None:
    port: StoryGrouper = grouper()
    assert port.group([]) == []


# --- TC-3: reworded headlines about one event are one group --------------------------
def test_every_real_same_event_pair_becomes_one_group(pairs: dict[str, Any]) -> None:
    same = [p for p in pairs["pairs"] if p["same"]]
    assert len(same) >= 9
    for p in same:
        a, b = article(p["a"]), article(p["b"])
        groups = grouper().group([a, b])
        assert len(groups) == 1, f"{p['why']}: {a.title!r} / {b.title!r}"
        (g,) = groups
        assert g.sources == a.source_count + b.source_count
        assert ids(g) == {a.article_id, b.article_id}


def test_the_shown_headline_has_the_most_sources_and_the_rest_are_also(
    pairs: dict[str, Any],
) -> None:
    murphy = next(
        p for p in pairs["pairs"] if "Murphy" in p["a"]["title"] and p["same"]
    )
    a, b = article(murphy["a"]), article(murphy["b"])
    (g,) = grouper().group([b, a])  # input order does not matter
    top, other = (a, b) if a.source_count >= b.source_count else (b, a)
    assert g.shown.article_id == top.article_id
    assert [x.article_id for x in g.also] == [other.article_id]


def test_equal_sources_show_the_newest_headline(
    make_article: Callable[..., Article],
) -> None:
    old = make_article(
        1,
        title="Storm batters the northern coast overnight",
        source_count=4,
        domain="a.com",
        published_at=NOW - timedelta(hours=3),
    )
    new = make_article(
        2,
        title="Storm batters northern coast overnight again",
        source_count=4,
        domain="b.com",
        published_at=NOW,
    )
    (g,) = grouper().group([old, new])
    assert g.shown.article_id == new.article_id
    assert [x.article_id for x in g.also] == [old.article_id]
    assert g.sources == 8


def test_also_is_ordered_by_sources_then_newest(
    make_article: Callable[..., Article],
) -> None:
    base = "Flood waters rise across the river valley towns"
    items = [
        make_article(1, title=base, source_count=9, domain="a.com", published_at=NOW),
        make_article(
            2,
            title=base + " today",
            source_count=2,
            domain="b.com",
            published_at=NOW - timedelta(hours=1),
        ),  # fmt: skip
        make_article(
            3, title=base + " tonight", source_count=5, domain="c.com", published_at=NOW
        ),  # fmt: skip
        make_article(
            4, title=base + " again", source_count=2, domain="d.com", published_at=NOW
        ),  # fmt: skip
    ]
    (g,) = grouper().group(items)
    assert g.sources == 18
    assert g.shown.article_id == "id1"
    assert [x.article_id for x in g.also] == ["id3", "id4", "id2"]


# --- TC-4: different events stay apart -----------------------------------------------
def test_every_real_different_pair_stays_two_groups(pairs: dict[str, Any]) -> None:
    different = [p for p in pairs["pairs"] if not p["same"]]
    assert len(different) >= 5
    for p in different:
        a, b = article(p["a"]), article(p["b"])
        assert len(grouper().group([a, b])) == 2, (
            f"{p['why']}: {a.title!r} / {b.title!r}"
        )


def test_template_headlines_from_one_domain_stay_separate(
    pairs: dict[str, Any],
) -> None:
    rows = [article(r) for r in pairs["same_domain_template"]]
    assert len(rows) >= 3
    assert len({r.domain for r in rows}) == 1
    assert len(grouper().group(rows)) == len(rows)


def test_the_same_template_headlines_would_merge_without_the_domain_guard(
    pairs: dict[str, Any],
) -> None:
    """Proves the guard is what keeps them apart (the tokens alone match)."""
    rows = [article(r) for r in pairs["same_domain_template"]]
    other_domains = [
        r.model_copy(update={"domain": f"site{i}.com"}) for i, r in enumerate(rows)
    ]
    assert len(grouper().group(other_domains)) < len(rows)


def test_a_missing_domain_never_blocks_a_merge(
    make_article: Callable[..., Article],
) -> None:
    a = make_article(
        1,
        title="Council approves new harbour dredging plan",
        domain=None,
        source_count=3,
    )
    b = make_article(
        2,
        title="Council approves harbour dredging plan after vote",
        domain=None,
        source_count=2,
    )
    assert len(grouper().group([a, b])) == 1


def test_unrelated_headlines_with_shared_common_words_stay_apart(
    make_article: Callable[..., Article],
) -> None:
    items = [
        make_article(
            1, title="Company announces new chief executive appointment", domain="a.com"
        ),
        make_article(
            2, title="Company announces quarterly dividend increase", domain="b.com"
        ),
    ]
    assert len(grouper().group(items)) == 2


def test_no_chaining_a_member_is_never_compared_to_other_members(
    make_article: Callable[..., Article],
) -> None:
    a = make_article(
        1, title="alpha beta gamma delta epsilon", source_count=9, domain="a.com"
    )
    b = make_article(
        2, title="beta gamma delta epsilon zeta", source_count=5, domain="b.com"
    )
    c = make_article(
        3, title="gamma delta epsilon zeta eta", source_count=2, domain="c.com"
    )
    # a~b and b~c match, a~c does not: c must not ride in through b
    assert matches(title_tokens(a.title), title_tokens(b.title), MatchParams())
    assert matches(title_tokens(b.title), title_tokens(c.title), MatchParams())
    assert not matches(title_tokens(a.title), title_tokens(c.title), MatchParams())
    groups = grouper().group([c, b, a])
    assert sorted(ids(g) for g in groups) == [{"id1", "id2"}, {"id3"}]


# --- TC-5: the time window -----------------------------------------------------------
def pair_at(
    make_article: Callable[..., Article], gap: timedelta
) -> tuple[Article, Article]:
    title = "Parliament passes sweeping new coastal protection law"
    a = make_article(1, title=title, source_count=5, domain="a.com", published_at=NOW)
    b = make_article(
        2,
        title=title + " today",
        source_count=3,
        domain="b.com",
        published_at=NOW - gap,
    )
    return a, b


def test_inside_the_window_merges_and_outside_does_not(
    make_article: Callable[..., Article],
) -> None:
    inside = pair_at(make_article, timedelta(hours=47, minutes=59))
    outside = pair_at(make_article, timedelta(hours=48, minutes=1))
    assert len(grouper().group(list(inside))) == 1
    assert len(grouper().group(list(outside))) == 2


def test_the_window_is_a_parameter(make_article: Callable[..., Article]) -> None:
    pair = pair_at(make_article, timedelta(hours=47, minutes=59))
    assert len(grouper(timedelta(hours=24)).group(list(pair))) == 2


def test_the_window_applies_to_the_seed_in_both_directions(
    make_article: Callable[..., Article],
) -> None:
    title = "Parliament passes sweeping new coastal protection law"
    seed = make_article(
        1, title=title, source_count=9, domain="a.com", published_at=NOW
    )
    later = make_article(2, title=title + " now", source_count=2, domain="b.com",
                         published_at=NOW + timedelta(hours=49))  # fmt: skip
    assert len(grouper().group([seed, later])) == 2


# --- determinism and the index -------------------------------------------------------
def test_input_order_does_not_change_the_groups(pairs: dict[str, Any]) -> None:
    rows = [article(p[side]) for p in pairs["pairs"] for side in ("a", "b")]
    rows += [article(r) for r in pairs["same_domain_template"]]
    unique = list({r.article_id: r for r in rows}.values())
    reference = sorted(sorted(ids(g)) for g in grouper().group(unique))
    for seed in range(5):
        shuffled = unique[:]
        random.Random(seed).shuffle(shuffled)
        assert sorted(sorted(ids(g)) for g in grouper().group(shuffled)) == reference


def brute_force(
    articles: Sequence[Article], params: MatchParams, window: timedelta
) -> list[set[str]]:
    """The same rules without the token index: compare with every existing group."""
    order = sorted(
        articles, key=lambda a: (-a.source_count, a.published_at, a.article_id)
    )
    groups: list[tuple[Article, set[str], list[str]]] = []
    for art in order:
        for seed, domains, members in groups:
            if art.domain is not None and art.domain in domains:
                continue
            if abs(art.published_at - seed.published_at) > window:
                continue
            if matches(title_tokens(seed.title), title_tokens(art.title), params):
                members.append(art.article_id)
                if art.domain is not None:
                    domains.add(art.domain)
                break
        else:
            groups.append(
                (art, {art.domain} if art.domain else set(), [art.article_id])
            )
    return [set(members) for _, _, members in groups]


@pytest.fixture(scope="module")
def real_hour() -> list[Article]:
    raw = json.loads((FIXTURES / "story_window.json").read_text())
    return [article(r) for r in raw]


def test_the_index_gives_the_same_groups_as_brute_force_on_a_real_hour(
    real_hour: list[Article],
) -> None:
    assert len(real_hour) > 1500
    indexed = sorted(sorted(ids(g)) for g in grouper().group(real_hour))
    reference = sorted(sorted(g) for g in brute_force(real_hour, MatchParams(), WINDOW))
    assert indexed == reference


def test_a_real_hour_groups_quickly_and_merges_something(
    real_hour: list[Article],
) -> None:
    start = time.perf_counter()
    groups = grouper().group(real_hour)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0  # measured at 0.02 s; M-1 records the real number
    assert len(groups) < len(real_hour)  # some headlines were merged
    assert sum(g.sources for g in groups) == sum(a.source_count for a in real_hour)


# --- group helpers used by the renderer (T-05) -----------------------------------
def test_a_group_key_is_its_seed_id_and_is_stable(
    make_article: Callable[..., Article],
) -> None:
    title = "Council approves new harbour dredging plan after vote"
    big = make_article(1, title=title, source_count=9, domain="a.com", published_at=NOW)
    small = make_article(
        2, title=title + " today", source_count=2, domain="b.com", published_at=NOW
    )
    (g,) = grouper().group([small, big])
    assert g.key == g.seed.article_id == "id1"


def test_variants_are_distinct_cleaned_headlines_shown_one_first(
    make_article: Callable[..., Article],
) -> None:
    base = "Storm batters the northern coast overnight"
    items = [
        make_article(1, title=base, source_count=9, domain="a.com", published_at=NOW),
        make_article(
            2,
            title=base + " | Daily Gazette",
            source_count=8,
            domain="b.com",
            published_at=NOW,
        ),
        make_article(
            3, title=base + " again", source_count=7, domain="c.com", published_at=NOW
        ),
    ]
    (g,) = grouper().group(items)
    assert g.sources == 24  # every copy still counts as coverage
    assert [v.article_id for v in g.variants] == ["id1", "id3"]  # id2 repeats id1
    assert [v.article_id for v in g.also] == ["id3"]
