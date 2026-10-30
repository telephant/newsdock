"""Markdown renderer (TC-8 rendered side, TC-11, TC-12, TC-13; AC-5, AC-7, AC-8)."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

from whathappen.domain.articles import Article
from whathappen.domain.baseline import Baseline
from whathappen.domain.render import (
    render_digest,
    story_line,
    theme_label,
)
from whathappen.domain.stories import ThemePick, pick_stories
from whathappen.domain.themes import RankedTheme, count_themes, rank_themes

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "digest_window.json"
NOW = datetime(2026, 10, 30, 14, 7, tzinfo=UTC)
SINCE = datetime(2026, 10, 30, 13, 7, tzinfo=UTC)
SPECIAL = set("\\[]`*_<>|&#")


def parse_story_line(line: str) -> tuple[str, str, str]:
    """A tiny CommonMark-link reader: returns (title, url, rest after the link)."""
    assert line.startswith("- [")
    i, text = 3, ""
    while True:
        ch = line[i]
        if ch == "\\":
            nxt = line[i + 1]
            assert nxt in SPECIAL, f"unexpected escape \\{nxt}"
            text += nxt
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
    return text, url, line[end + 1 :]


def theme_pick(
    code: str, shown: list[Article], count: int = 12, rise: float | None = None
) -> ThemePick:
    return ThemePick(RankedTheme(code, count, rise), shown, shown)


# ---- TC-11: escaping ------------------------------------------------------------


def test_tc11_hostile_title_and_url_round_trip_through_one_line(
    make_article: Callable[..., Article],
) -> None:
    title = "A [b] \\ *c* _d_ `e` <f> g|h #i &copy;\nsecond line &#x2013; end"
    url = "https://example.com/a (b)/c)d?x=<1>"
    line = story_line(make_article(1, title=title, url=url, source_count=3))
    assert "\n" not in line
    text, parsed_url, rest = parse_story_line(line)
    assert text == "A [b] \\ *c* _d_ `e` <f> g|h #i © second line – end"
    assert unquote(parsed_url) == url
    assert rest == " · example.com · 3 sources"


def test_tc11_html_entities_are_decoded_once(
    make_article: Callable[..., Article],
) -> None:
    line = story_line(make_article(1, title="Robinson hopes &#x2013; and &amp;amp;"))
    text, _, _ = parse_story_line(line)
    assert text == "Robinson hopes – and &amp;"  # one decode, not two


# ---- TC-12: line variants -----------------------------------------------------------


def test_tc12_singular_plural_and_missing_domain(
    make_article: Callable[..., Article],
) -> None:
    one = story_line(make_article(1, source_count=1))
    many = story_line(make_article(2, source_count=14))
    none = story_line(make_article(3, source_count=2, domain=None))
    assert one.endswith(" · example.com · 1 source")
    assert many.endswith(" · example.com · 14 sources")
    assert none.endswith(" · 2 sources") and "None" not in none
    assert "·  ·" not in none


def test_tc12_a_title_empty_after_cleaning_is_shown_as_the_url(
    make_article: Callable[..., Article],
) -> None:
    line = story_line(make_article(1, title="  \n\t ", url="https://example.com/x"))
    text, url, _ = parse_story_line(line)
    assert text == "https://example.com/x" and url == "https://example.com/x"


def test_theme_label_replaces_underscores() -> None:
    assert theme_label("ECON_INFLATION") == "ECON INFLATION"


# ---- TC-13 / TC-8: layout ------------------------------------------------------


def three_themes(make_article: Callable[..., Article]) -> list[ThemePick]:
    return [
        theme_pick(
            "ECON_INFLATION",
            [make_article(1, source_count=14), make_article(2, source_count=9)],
            count=58,
            rise=3.44,
        ),
        theme_pick("PROTEST", [make_article(3)], count=1, rise=2.1),
        theme_pick("ELECTION", [make_article(4)], count=31, rise=1.0),
    ]


def classify(text: str) -> list[str]:
    kinds: list[str] = []
    after_section = False
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("## "):
            kinds.append("section")
            after_section = True
        elif line.startswith("# "):
            kinds.append("title")
        elif line.startswith("> "):
            kinds.append("notice")
        elif line.startswith("- ["):
            kinds.append("story")
            after_section = False
        else:
            assert after_section, f"stray line: {line!r}"
            kinds.append("summary")
            after_section = False
    return kinds


def test_tc13_layout_heading_notice_sections_in_rank_order(
    make_article: Callable[..., Article],
) -> None:
    text = render_digest(
        now=NOW,
        article_count=1840,
        since=SINCE,
        picks=three_themes(make_article),
        summaries={
            "ECON_INFLATION": "Prices ease.",
            "PROTEST": None,
            "ELECTION": "Vote.",
        },
    )
    lines = text.splitlines()
    assert (
        lines[0]
        == "# What happened · 2026-10-30 14:07 UTC (1840 articles · since 13:07)"
    )
    assert lines[2].startswith("> From headlines only.")
    assert classify(text) == [
        "title", "notice",
        "section", "summary", "story", "story",
        "section", "summary", "story",
        "section", "summary", "story",
    ]  # fmt: skip
    sections = [ln for ln in lines if ln.startswith("## ")]
    assert sections[0] == "## 1. ECON INFLATION · ×3.4 vs usual · 58 stories"
    assert sections[1] == "## 2. PROTEST · ×2.1 vs usual · 1 story"
    assert "Summary unavailable." in lines  # the None summary
    assert "Prices ease." in lines
    assert text.endswith("\n")


def test_tc13_first_run_and_other_day_since_labels(
    make_article: Callable[..., Article],
) -> None:
    picks = three_themes(make_article)[:1]
    first = render_digest(
        now=NOW, article_count=5, since=None, picks=picks, summaries={}
    )
    assert "(5 articles · first run)" in first.splitlines()[0]
    yesterday = datetime(2026, 10, 29, 23, 7, tzinfo=UTC)
    other = render_digest(
        now=NOW, article_count=5, since=yesterday, picks=picks, summaries={}
    )
    assert "since 10-29 23:07)" in other.splitlines()[0]


def test_tc8_cold_start_sections_say_no_baseline_yet(
    make_article: Callable[..., Article],
) -> None:
    picks = [theme_pick("ECON_INFLATION", [make_article(1)], count=58, rise=None)]
    text = render_digest(
        now=NOW, article_count=9, since=None, picks=picks, summaries={}
    )
    assert "## 1. ECON INFLATION · no baseline yet · 58 stories" in text
    assert "vs usual" not in text


def test_a_theme_without_stories_is_left_out_and_the_rest_renumbered(
    make_article: Callable[..., Article],
) -> None:
    picks = [
        theme_pick("EMPTY", [], count=9, rise=5.0),
        theme_pick("ECON_INFLATION", [make_article(1)], count=58, rise=1.0),
    ]
    text = render_digest(
        now=NOW, article_count=9, since=None, picks=picks, summaries={}
    )
    assert "EMPTY" not in text
    assert "## 1. ECON INFLATION" in text


def test_a_hostile_summary_stays_one_plain_line(
    make_article: Callable[..., Article],
) -> None:
    picks = [theme_pick("T", [make_article(1)], count=9, rise=1.0)]
    text = render_digest(
        now=NOW,
        article_count=9,
        since=None,
        picks=picks,
        summaries={"T": "# Big [x](http://evil) <b>bold</b>\nnext"},
    )
    summary = text.splitlines()[
        text.splitlines().index("## 1. T · ×1.0 vs usual · 9 stories") + 2
    ]
    assert "\n" not in summary
    assert not summary.startswith("#")
    assert "<b>" not in summary and "](http" not in summary.replace("\\]", "")


def test_tc13_real_sample_window_renders_a_clean_digest() -> None:
    raw = json.loads(FIXTURE.read_text())
    articles = [Article.from_mcp(r) for r in raw]
    counts = count_themes(articles)
    ranked = rank_themes(
        counts,
        len(articles),
        Baseline(),
        skip_prefixes=("TAX_", "WB_", "EPU_"),
        min_count=2,
        max_themes=3,
        min_entries=3,
    )
    picks = pick_stories(ranked, articles, per_theme=3, prompt_titles=8)
    text = render_digest(
        now=NOW, article_count=len(articles), since=None, picks=picks, summaries={}
    )
    kinds = classify(text)
    assert kinds[:2] == ["title", "notice"]
    assert kinds.count("section") >= 1
    for line in text.splitlines():
        if line.startswith("- ["):
            parse_story_line(line)  # every story line parses back
    assert "&#x" not in text  # entities decoded
