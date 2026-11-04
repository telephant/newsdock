"""TC-7 (render half), TC-10 (quiet note), TC-13, TC-19 (AC-6, AC-8, AC-11): the
story-first renderer."""

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

from whathappen.domain.articles import Article
from whathappen.domain.grouping import StoryGroup
from whathappen.domain.render import MARKER, render_story_digest
from whathappen.domain.scoring import (
    RANKING_COVERAGE,
    RANKING_TONE,
    ScoredGroup,
    score_groups,
)
from whathappen.domain.sections import Section, Selection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NOW = datetime(2026, 11, 2, 14, 7, tzinfo=UTC)
SPECIAL = set("\\[]`*_<>|&#~")
MakeArticle = Callable[..., Article]
Golden = tuple[Selection, dict[str, str]]


def read_links(line: str) -> list[tuple[str, str]]:
    """A tiny CommonMark-link reader: every `[text](url)` in the line, strictly."""
    links: list[tuple[str, str]] = []
    i = 0
    while i < len(line):
        if line[i] != "[":
            i += 1
            continue
        i += 1
        text = ""
        while True:
            ch = line[i]
            if ch == "\\":
                assert line[i + 1] in SPECIAL, f"unexpected escape \\{line[i + 1]}"
                text += line[i + 1]
                i += 2
            elif ch == "]":
                break
            else:
                assert ch not in SPECIAL, f"unescaped {ch!r} in link text"
                text += ch
                i += 1
        assert line[i + 1] == "("
        end = line.index(")", i + 2)
        url = line[i + 2 : end]
        assert not set(url) & {" ", "(", "<", ">"}
        links.append((text, url))
        i = end + 1
    return links


def story(
    make: MakeArticle, n: int, title: str, sources: int, domain: str | None = None
) -> Article:
    return make(
        n,
        title=title,
        url=f"https://{domain or 'x.example'}/{n}",
        domain=domain,
        source_count=sources,
    )


def scored(group: StoryGroup) -> ScoredGroup:
    return ScoredGroup(group, group.sources, None, float(group.sources))


def render(
    selection: Selection,
    *,
    ranking: str = RANKING_TONE,
    summaries: Mapping[str, str | None] | None = None,
    articles: int = 1920,
    min_sources: int = 2,
    also: int = 3,
) -> str:
    return render_story_digest(
        now=NOW,
        article_count=articles,
        selection=selection,
        ranking=ranking,
        summaries=summaries or {},
        min_sources=min_sources,
        also_limit=also,
    )


def two_headlines(make: MakeArticle) -> StoryGroup:
    return StoryGroup(
        (
            story(make, 1, "Flood waters rise across the river valley", 9, "a.com"),
            story(make, 2, "Flood waters rise across river valley towns", 5, "b.com"),
        )
    )


@pytest.fixture
def golden(make_article: MakeArticle) -> Golden:
    murphy = StoryGroup(
        (
            make_article(
                1, title="Senator hospitalised after stroke", source_count=61,
                url="https://ct.example/a", domain="ct.example",
            ),
            make_article(
                2, title="Senator Murphy suffers stroke", source_count=30,
                url="https://wire.example/b", domain="wire.example",
            ),
            make_article(
                3, title="US senator in hospital", source_count=21,
                url="https://us.example/c", domain="us.example",
            ),
        )
    )  # fmt: skip
    jet = StoryGroup(
        (
            make_article(
                4, title="Jet crash kills nine near Florida road", source_count=61,
                url="https://fl.example/d", domain="fl.example",
            ),
        )
    )  # fmt: skip
    ruling = StoryGroup(
        (
            make_article(
                5, title="Judge dismisses Alaska certification suit", source_count=34,
                url="https://ak.example/e", domain="ak.example",
            ),
        )
    )  # fmt: skip
    hall = StoryGroup(
        (
            make_article(
                6, title="Hall opens at shipyard", source_count=30,
                url="https://uk.example/f", domain="uk.example",
            ),
        )
    )  # fmt: skip
    selection = Selection(
        top=(scored(murphy), scored(jet)),
        sections=(
            Section("Politics & Government", (scored(ruling),)),
            Section("Other", (scored(hall),)),
        ),
    )
    return selection, {murphy.key: "The senator was taken to hospital after a stroke."}


# --- TC-19: the exact file ---------------------------------------------------------
def test_the_golden_file(golden: Golden) -> None:
    selection, summaries = golden
    text = render(selection, summaries=summaries)
    assert text == (FIXTURES / "digest_golden.md").read_text()


# --- layout rules ------------------------------------------------------------------
def test_marker_first_then_one_heading_then_the_notice(golden: Golden) -> None:
    lines = render(golden[0]).splitlines()
    assert lines[0] == MARKER == "<!-- whathappen:story-first -->"
    assert lines[1].startswith("# What happened · 2026-11-02 14:07 UTC (1920 new")
    assert sum(1 for line in lines if line.startswith("# ")) == 1
    assert lines[3].startswith("> New this hour, from headlines only.")
    assert lines[4].startswith("> Summaries are written by a small local model")


def test_the_notice_names_the_ranking_used(golden: Golden) -> None:
    selection = golden[0]
    tone = render(selection, ranking=RANKING_TONE)
    assert "Ranked by outlets covering a story and negative tone." in tone
    coverage = render(selection, ranking=RANKING_COVERAGE)
    assert "Ranked by outlets covering a story." in coverage
    assert "negative tone" not in coverage


def test_the_heading_counts_the_listed_stories(golden: Golden) -> None:
    assert "(1920 new articles · 4 stories)" in render(golden[0])
    one = Selection(top=golden[0].top[:1], sections=())
    assert "(1 new article · 1 story)" in render(one, articles=1)


def test_top_stories_are_numbered_and_sections_are_bulleted(golden: Golden) -> None:
    lines = render(golden[0]).splitlines()
    assert any(line.startswith("1. [") for line in lines)
    assert any(line.startswith("2. [") for line in lines)
    assert sum(1 for line in lines if line.startswith("- [")) == 2
    assert [line for line in lines if line.startswith("## ")] == [
        "## Top stories",
        "## Politics & Government",
        "## Other",
    ]


def test_each_story_appears_once(golden: Golden) -> None:
    text = render(golden[0])
    for tail in ("a", "d", "e", "f"):
        assert text.count(f"/{tail})") == 1


def test_one_source_is_singular_and_a_missing_domain_is_left_out(
    make_article: MakeArticle,
) -> None:
    g = StoryGroup((story(make_article, 1, "Lone story", 1),))
    text = render(Selection(top=(scored(g),), sections=()), min_sources=1)
    line = next(line for line in text.splitlines() if line.startswith("1. ["))
    assert line.endswith(" · 1 source")
    assert line.count(" · ") == 1  # only the source count follows the link
    assert "None" not in line


def test_also_is_limited_and_collapses_titles_that_differ_only_by_outlet(
    make_article: MakeArticle,
) -> None:
    base = "Storm batters the northern coast overnight"
    g = StoryGroup(
        (
            story(make_article, 1, base, 9, "a.com"),
            story(make_article, 2, base + " | Daily Gazette", 8, "b.com"),
            story(make_article, 3, base + " again", 7, "c.com"),
            story(make_article, 4, base + " tonight", 6, "d.com"),
            story(make_article, 5, base + " now", 5, "e.com"),
        )
    )
    text = render(Selection(top=(scored(g),), sections=()), also=2)
    (also_line,) = [line for line in text.splitlines() if "Also:" in line]
    assert [t for t, _ in read_links(also_line)] == [
        base + " again",
        base + " tonight",
    ]


# --- the model line ----------------------------------------------------------------
def test_every_summary_in_the_map_is_shown_whatever_the_headline_count(
    make_article: MakeArticle,
) -> None:
    """The cycle decides which groups get a sentence (a single headline gets one only
    with stored article text); render shows whatever the cycle wrote."""
    two = two_headlines(make_article)
    single = StoryGroup((story(make_article, 3, "A single headline here", 7, "c.com"),))
    text = render(
        Selection(top=(scored(two), scored(single)), sections=()),
        summaries={two.key: "Floods hit towns.", single.key: "A grounded sentence."},
    )
    assert "Floods hit towns." in text
    assert "A grounded sentence." in text


@pytest.mark.parametrize("bad", [None, "", "   \n "])
def test_a_missing_or_blank_summary_leaves_no_line(
    make_article: MakeArticle, bad: str | None
) -> None:
    two = two_headlines(make_article)
    text = render(Selection(top=(scored(two),), sections=()), summaries={two.key: bad})
    lines = text.splitlines()
    top = lines.index("## Top stories")
    assert lines[top + 1].startswith("1. [")
    assert lines[top + 2].startswith("   Also:")  # no model line in between


# --- quiet hour --------------------------------------------------------------------
def test_an_hour_without_a_widely_covered_story_says_so() -> None:
    text = render(Selection(top=(), sections=()), articles=1800)
    assert "(1800 new articles · 0 stories)" in text
    assert "No story was carried by 2 or more outlets this hour." in text
    assert "## " not in text
    assert text.splitlines()[0] == MARKER


def test_the_quiet_hour_sentence_follows_the_configured_minimum() -> None:
    text = render(Selection((), ()), min_sources=3)
    assert "carried by 3 or more outlets" in text


# --- TC-13: hostile text -----------------------------------------------------------
HOSTILE_TITLE = "A [b] \\ *c* _d_ `e` <f> g|h #i &copy;\nsecond line &#x2013; end"
HOSTILE_URL = "https://example.com/a (b)/c)d?x=<1>"


def hostile_group(make: MakeArticle, n: int, other_title: str) -> StoryGroup:
    first = make(
        n, title=HOSTILE_TITLE, url=HOSTILE_URL, domain="ex<b>.com", source_count=5
    )
    other = make(
        n + 10, title=other_title, url=HOSTILE_URL + "2", domain="y.com", source_count=3
    )
    return StoryGroup((first, other))


def test_hostile_text_is_one_well_formed_link_in_the_top_block_and_a_section(
    make_article: MakeArticle,
) -> None:
    top = hostile_group(make_article, 1, "A [b] *c* different headline!")
    sec = hostile_group(make_article, 2, "Same *event* [again]")
    text = render(
        Selection(top=(scored(top),), sections=(Section("Other", (scored(sec),)),)),
        summaries={
            top.key: "Ignore previous *instructions* <script>",
            sec.key: "[x](http://evil)",
        },
    )
    assert "\n\n\n" not in text
    for line in text.splitlines():
        if line.startswith(("1. [", "- [")) or "Also:" in line:
            for title, url in read_links(line):
                assert unquote(url).startswith(HOSTILE_URL)
                assert "\n" not in title
    first = next(line for line in text.splitlines() if line.startswith("1. ["))
    ((title, _),) = read_links(first)
    assert title == "A [b] \\ *c* _d_ `e` <f> g|h #i © second line – end"
    # the model line is escaped text, not markup
    model = next(line for line in text.splitlines() if "instructions" in line)
    assert "\\*instructions\\*" in model and "\\<script\\>" in model
    assert "\\[x\\]" in text and "[x](http://evil)" not in text


def test_a_title_is_decoded_once_not_twice(make_article: MakeArticle) -> None:
    g = StoryGroup(
        (story(make_article, 1, "Robinson hopes &#x2013; and &amp;amp;", 4),)
    )
    text = render(Selection(top=(scored(g),), sections=()))
    line = next(line for line in text.splitlines() if line.startswith("1. ["))
    ((title, _),) = read_links(line)
    assert title == "Robinson hopes – and &amp;"


def test_the_output_has_one_trailing_newline_and_no_blank_runs(golden: Golden) -> None:
    text = render(golden[0])
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert re.search(r"\n\n\n", text) is None


def test_group_keys_are_stable_and_unique(golden: Golden) -> None:
    items: Sequence[ScoredGroup] = [
        *golden[0].top,
        *(g for s in golden[0].sections for g in s.groups),
    ]
    keys = [s.group.key for s in items]
    assert len(set(keys)) == len(keys) == 4
    ranked, _ = score_groups([s.group for s in items], 10)
    assert {s.group.key for s in ranked} == set(keys)
