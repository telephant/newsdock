"""DigestCycle (TC-10, 11, 12, 14, 15; AC-2, AC-8, AC-9, AC-10, AC-12): one cycle
against fake ports, with the real lexical grouper."""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from whathappen.domain.articles import Article
from whathappen.domain.digest import Digest, DigestCycle, DigestParams
from whathappen.domain.grouping import LexicalGrouper
from whathappen.domain.render import MARKER
from whathappen.domain.titles import MatchParams

NOW = datetime(2026, 11, 2, 14, 7, tzinfo=UTC)
LABELS = (("Politics & Government", ("ELECTION",)),)
MakeArticle = Callable[..., Article]


def params(**overrides: object) -> DigestParams:
    base: dict[str, object] = {
        "page_size": 200,
        "max_articles": 20000,
        "min_group_sources": 2,
        "top_stories": 5,
        "max_sections": 6,
        "groups_per_section": 4,
        "also_per_group": 3,
        "section_min_hits": 1,
        "tone_divisor": 10.0,
        "labels": LABELS,
    }
    base.update(overrides)
    return DigestParams(**base)  # type: ignore[arg-type]


class Events(list[str]):
    """One shared log so the call order across the ports can be asserted."""


class FakeMcp:
    """Scripted pages; page i has cursor f'c{i + 1}'. Beyond the script: empty.
    `bodies` scripts `get_article` by article id; an unknown id has no body row."""

    def __init__(
        self,
        events: Events,
        pages: list[list[dict[str, object]]],
        bodies: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.events = events
        self.pages = pages
        self.bodies = bodies or {}
        self.get_fails = False
        self.list_calls: list[tuple[int, str | None, Sequence[str] | None]] = []
        self.article_calls: list[str] = []
        self.acks: list[str] = []

    def list_new_articles(
        self,
        limit: int,
        cursor: str | None = None,
        include: Sequence[str] | None = None,
    ) -> tuple[list[dict[str, object]], str]:
        self.list_calls.append((limit, cursor, include))
        self.events.append("list")
        i = len(self.list_calls) - 1
        if i < len(self.pages):
            return self.pages[i], f"c{i + 1}"
        return [], cursor or "c0"

    def get_article(self, article_id: str) -> dict[str, object]:
        self.events.append(f"get:{article_id}")
        self.article_calls.append(article_id)
        if self.get_fails:
            raise RuntimeError("platform down")
        return self.bodies.get(article_id, {"body_status": "none", "body": None})

    def ack_cursor(self, cursor: str) -> None:
        self.events.append(f"ack:{cursor}")
        self.acks.append(cursor)


class FakeSink:
    def __init__(self, events: Events, fail: bool = False) -> None:
        self.events = events
        self.fail = fail
        self.writes: list[tuple[datetime, str]] = []

    def write(self, now: datetime, text: str) -> Path:
        if self.fail:
            raise OSError("disk full")
        self.events.append("write")
        self.writes.append((now, text))
        return Path("/digests/fake.md")


class FakeSummariser:
    """Answers `About: <first title>` unless told to fail or return nothing."""

    def __init__(
        self, raises: set[str] | None = None, nothing: set[str] | None = None
    ) -> None:
        self.raises = raises or set()
        self.nothing = nothing or set()
        self.calls: list[list[str]] = []
        self.excerpts: list[str | None] = []

    def summarise(
        self, titles: Sequence[str], excerpt: str | None = None
    ) -> str | None:
        self.calls.append(list(titles))
        self.excerpts.append(excerpt)
        first = titles[0]
        if first in self.raises:
            raise RuntimeError("model exploded")
        if first in self.nothing:
            return None
        return f"About: {first}"


def raw(article: Article, *, tone_key: bool = True) -> dict[str, object]:
    data = article.model_dump(mode="json")
    if not tone_key:
        data.pop("tone_neg")
    return data


def event(
    make: MakeArticle,
    start: int,
    base: str,
    sources: Sequence[int],
    themes: list[str] | None = None,
    tone: float | None = None,
) -> list[Article]:
    """One event reported with slightly different headlines by different outlets."""
    endings = ["", " today", " tonight", " again", " now", " live", " update"]
    return [
        make(
            start + i,
            title=base + endings[i],
            source_count=count,
            domain=f"outlet{start + i}.com",
            url=f"https://outlet{start + i}.com/{start + i}",
            themes=themes or [],
            tone_neg=tone,
        )
        for i, count in enumerate(sources)
    ]


def run(
    pages: list[list[dict[str, object]]],
    *,
    summariser: FakeSummariser | None = None,
    sink_fails: bool = False,
    bodies: dict[str, dict[str, object]] | None = None,
    **overrides: object,
) -> tuple[FakeMcp, FakeSink, FakeSummariser, Events, Digest | None]:
    events = Events()
    mcp, sink = FakeMcp(events, pages, bodies), FakeSink(events, fail=sink_fails)
    model = summariser or FakeSummariser()
    grouper = LexicalGrouper(MatchParams(), timedelta(hours=48))
    cycle = DigestCycle(mcp, grouper, model, sink, params(**overrides))
    return mcp, sink, model, events, cycle.run_once(NOW)


FLOOD = "Flood waters rise across the river valley towns"
STORM = "Storm batters the northern coast overnight causing damage"
COUNCIL = "Council approves new harbour dredging plan after vote"


# ---- TC-15: reading the window and asking for tone ---------------------------------
def test_every_page_is_read_in_order_and_every_call_asks_for_tone(
    make_article: MakeArticle,
) -> None:
    def page(start: int, n: int) -> list[dict[str, object]]:
        return [
            raw(make_article(start + i, title=f"Unrelated headline {start + i}"))
            for i in range(n)
        ]

    mcp, _, _, _, result = run([page(0, 200), page(200, 200), page(400, 37)])
    assert result is not None and result.article_count == 437
    assert mcp.list_calls == [
        (200, None, ["tone_neg"]),
        (200, "c1", ["tone_neg"]),
        (200, "c2", ["tone_neg"]),
    ]
    assert mcp.acks == ["c3"]


def test_a_full_last_page_means_one_more_empty_page_is_requested(
    make_article: MakeArticle,
) -> None:
    pages = [[raw(make_article(i, title=f"Headline number {i}")) for i in range(200)]]
    mcp, _, _, _, result = run(pages)
    assert result is not None
    assert [c[:2] for c in mcp.list_calls] == [(200, None), (200, "c1")]
    assert mcp.acks == ["c1"]


def test_paging_stops_at_the_article_cap_and_acks_what_was_read(
    make_article: MakeArticle,
) -> None:
    pages = [
        [raw(make_article(p * 200 + i, title=f"Headline {p}-{i}")) for i in range(200)]
        for p in range(3)
    ]
    mcp, _, _, _, result = run(pages, max_articles=300)
    assert result is not None and result.article_count == 400
    assert len(mcp.list_calls) == 2
    assert mcp.acks == ["c2"]


def test_an_empty_window_writes_and_acks_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    mcp, sink, model, events, result = run([])
    assert result is None
    assert sink.writes == [] and mcp.acks == [] and model.calls == []
    assert events == ["list"]
    assert any("empty window" in r.getMessage() for r in caplog.records)


def test_a_malformed_article_is_skipped_not_fatal(make_article: MakeArticle) -> None:
    good = raw(make_article(1, title="One good headline here", source_count=3))
    page: list[dict[str, object]] = [
        good,
        {"article_id": "bad", "title": "no url or date"},
    ]
    mcp, sink, _, _, result = run([page])
    assert result is not None and result.article_count == 1
    assert len(sink.writes) == 1 and mcp.acks == ["c1"]


def test_a_window_of_only_unreadable_rows_is_acked_without_a_digest() -> None:
    mcp, sink, _, _, result = run([[{"nonsense": 1}]])
    assert result is None and sink.writes == [] and mcp.acks == ["c1"]


def test_articles_without_the_tone_key_are_ranked_by_coverage(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5])
    _, sink, _, _, _ = run([[raw(a, tone_key=False) for a in flood]])
    text = sink.writes[0][1]
    assert "Ranked by outlets covering a story." in text
    assert "negative tone" not in text


def test_a_platform_that_returns_tone_is_ranked_by_coverage_and_tone(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5], tone=6.0)
    _, sink, _, _, _ = run([[raw(a) for a in flood]])
    assert "Ranked by outlets covering a story and negative tone." in sink.writes[0][1]


# ---- TC-14: file first, then ack ---------------------------------------------------
def test_the_file_is_written_before_the_one_ack(make_article: MakeArticle) -> None:
    storm = event(make_article, 1, STORM, [8, 4])
    mcp, sink, _, events, result = run([[raw(a) for a in storm]])
    assert events == ["list", "write", "ack:c1"]
    assert mcp.acks == ["c1"] and len(sink.writes) == 1
    assert result is not None and result.cursor == "c1"


def test_a_failed_write_means_no_ack_and_the_next_cycle_reads_the_window_again(
    make_article: MakeArticle,
) -> None:
    page = [raw(a) for a in event(make_article, 1, STORM, [8, 4])]
    events = Events()
    mcp = FakeMcp(events, [page])
    grouper = LexicalGrouper(MatchParams(), timedelta(hours=48))
    broken = DigestCycle(
        mcp, grouper, FakeSummariser(), FakeSink(events, fail=True), params()
    )
    with pytest.raises(OSError):
        broken.run_once(NOW)
    assert mcp.acks == []

    mcp2, sink2 = FakeMcp(Events(), [page]), FakeSink(Events())
    DigestCycle(mcp2, grouper, FakeSummariser(), sink2, params()).run_once(NOW)
    assert len(sink2.writes) == 1 and mcp2.acks == ["c1"]


# ---- TC-10: quiet hours and the minimum ---------------------------------------------
def test_an_hour_of_single_source_articles_still_writes_and_acks(
    make_article: MakeArticle,
) -> None:
    page = [
        raw(make_article(i, title=f"Unrelated singular story {i}")) for i in range(5)
    ]
    mcp, sink, model, events, result = run([page])
    assert result is not None
    text = sink.writes[0][1]
    assert text.startswith(MARKER)
    assert "No story was carried by 2 or more outlets this hour." in text
    assert "(5 new articles · 0 stories)" in text
    assert model.calls == []  # no model call for an empty selection
    assert events == ["list", "write", "ack:c1"]


def test_only_groups_with_enough_sources_are_listed(make_article: MakeArticle) -> None:
    covered = event(make_article, 1, FLOOD, [1, 1])  # two outlets: 2 sources together
    lone = [
        make_article(
            10, title="A completely separate quiet little story", source_count=1
        )
    ]
    _, sink, _, _, _ = run([[raw(a) for a in covered + lone]])
    text = sink.writes[0][1]
    assert FLOOD in text
    assert "A completely separate quiet little story" not in text
    assert "(3 new articles · 1 story)" in text


def test_the_minimum_is_a_setting(make_article: MakeArticle) -> None:
    lone = [make_article(1, title="A single outlet story", source_count=1)]
    _, sink, _, _, _ = run([[raw(a) for a in lone]], min_group_sources=1)
    assert "A single outlet story" in sink.writes[0][1]


def test_sections_come_from_the_label_map(make_article: MakeArticle) -> None:
    storm = event(make_article, 1, STORM, [20, 5])
    vote = event(make_article, 10, COUNCIL, [9, 4], themes=["ELECTION"])
    _, sink, _, _, _ = run([[raw(a) for a in storm + vote]], top_stories=1)
    text = sink.writes[0][1]
    top, rest = text.split("## Top stories")[1].split("## Politics & Government")
    assert STORM in top and COUNCIL in rest


# ---- TC-11: the model is asked only about groups with several headlines -------------
def test_the_model_sees_only_the_headlines_of_a_multi_headline_group(
    make_article: MakeArticle,
) -> None:
    multi = event(make_article, 1, FLOOD, [9, 5, 3])
    single = [
        make_article(20, title="A single widely covered headline", source_count=7)
    ]
    _, sink, model, _, _ = run([[raw(a) for a in multi + single]])
    assert len(model.calls) == 1
    assert sorted(model.calls[0]) == sorted(a.title for a in multi)
    assert model.calls[0][0] == multi[0].title  # the shown headline first
    text = sink.writes[0][1]
    assert f"About: {multi[0].title}" in text
    assert "About: A single widely covered headline" not in text
    assert "A single widely covered headline" in text  # but it is listed


def test_the_model_gets_at_most_the_shown_headline_plus_also_per_group(
    make_article: MakeArticle,
) -> None:
    many = event(make_article, 1, FLOOD, [9, 8, 7, 6, 5, 4])
    _, _, model, _, _ = run([[raw(a) for a in many]], also_per_group=2)
    assert len(model.calls[0]) == 3


# ---- TC-12: a failing model only costs its own line ----------------------------------
def test_a_failing_or_silent_model_degrades_only_that_groups_line(
    make_article: MakeArticle,
) -> None:
    a = event(make_article, 1, FLOOD, [30, 10])
    b = event(make_article, 10, STORM, [25, 10])
    c = event(make_article, 20, COUNCIL, [20, 10])
    model = FakeSummariser(raises={a[0].title}, nothing={b[0].title})
    mcp, sink, _, events, result = run([[raw(x) for x in a + b + c]], summariser=model)
    assert result is not None
    text = sink.writes[0][1]
    assert f"About: {c[0].title}" in text  # the healthy group keeps its line
    assert f"About: {a[0].title}" not in text and f"About: {b[0].title}" not in text
    for first in (a[0], b[0]):
        assert first.title in text  # links stay
    assert events == ["list", "write", "ack:c1"]
    assert mcp.acks == ["c1"]


def test_the_cycle_returns_the_digest_it_wrote(make_article: MakeArticle) -> None:
    storm = event(make_article, 1, STORM, [8, 4])
    _, sink, _, _, result = run([[raw(a) for a in storm]])
    assert result is not None
    assert result.text == sink.writes[0][1]
    assert result.path == Path("/digests/fake.md")


# ---- body-grounded summaries (get_article; body-extraction backlog) ------------------
def body(text: str) -> dict[str, object]:
    return {"body_status": "ok", "body": text}


def test_the_summary_is_grounded_in_the_shown_articles_stored_text(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5])
    mcp, sink, model, _, _ = run(
        [[raw(a) for a in flood]],
        bodies={"id1": body("Rivers burst their banks after days of rain. " * 5)},
        summary_body_chars=80,
    )
    assert mcp.article_calls == ["id1"]  # the shown headline's article, found at once
    (excerpt,) = model.excerpts
    assert excerpt is not None and excerpt.startswith("Rivers burst their banks")
    assert len(excerpt) <= 80 and excerpt.endswith("…")  # clipped at a word boundary
    assert f"About: {flood[0].title}" in sink.writes[0][1]


def test_a_pending_body_falls_back_to_the_next_distinct_headline(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5, 3])
    bodies: dict[str, dict[str, object]] = {
        "id1": {"body_status": "pending", "body": None},
        "id2": body("The valley towns were evacuated overnight."),
    }
    mcp, _, model, _, _ = run(
        [[raw(a) for a in flood]], bodies=bodies, summary_body_chars=400
    )
    assert mcp.article_calls == ["id1", "id2"]
    assert model.excerpts == ["The valley towns were evacuated overnight."]


def test_the_lookup_stops_at_body_lookups_per_group(make_article: MakeArticle) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5, 3, 2])
    mcp, _, model, _, _ = run(
        [[raw(a) for a in flood]], summary_body_chars=400, body_lookups_per_group=2
    )
    assert mcp.article_calls == ["id1", "id2"]  # no body anywhere: give up after 2
    assert model.excerpts == [None]  # the headlines are still summarised


def test_a_failing_get_article_costs_only_the_excerpt_never_the_digest(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5])
    events = Events()
    mcp = FakeMcp(events, [[raw(a) for a in flood]])
    mcp.get_fails = True
    sink, model = FakeSink(events), FakeSummariser()
    grouper = LexicalGrouper(MatchParams(), timedelta(hours=48))
    cycle = DigestCycle(mcp, grouper, model, sink, params(summary_body_chars=400))
    result = cycle.run_once(NOW)
    assert result is not None and len(sink.writes) == 1 and mcp.acks == ["c1"]
    assert mcp.article_calls == ["id1"]  # one failure gives the whole group up
    assert model.excerpts == [None]
    assert f"About: {flood[0].title}" in sink.writes[0][1]


def test_zero_summary_body_chars_never_calls_get_article(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5])
    mcp, _, model, _, _ = run([[raw(a) for a in flood]])  # params default: 0 = off
    assert mcp.article_calls == []
    assert model.excerpts == [None]


def test_a_single_headline_story_with_stored_text_now_gets_a_sentence(
    make_article: MakeArticle,
) -> None:
    single = [make_article(1, title="A single widely covered headline", source_count=7)]
    mcp, sink, model, _, _ = run(
        [[raw(a) for a in single]],
        bodies={"id1": body("The agency confirmed the result on Monday.")},
        summary_body_chars=400,
    )
    assert "About: A single widely covered headline" in sink.writes[0][1]
    assert model.excerpts == ["The agency confirmed the result on Monday."]


def test_the_notice_names_article_text_only_when_grounding_is_on(
    make_article: MakeArticle,
) -> None:
    flood = event(make_article, 1, FLOOD, [9, 5])
    _, plain, _, _, _ = run([[raw(a) for a in flood]])
    _, grounded, _, _, _ = run([[raw(a) for a in flood]], summary_body_chars=400)
    assert "from headlines only" in plain.writes[0][1]
    assert "from headlines and stored article text" in grounded.writes[0][1]
