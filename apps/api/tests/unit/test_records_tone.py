"""TC-1 (AC-1), TC-4 (to_json part), TC-10 (unit part), AC-8 (detail fields):
the opt-in tone fields on the article records."""

from datetime import UTC, datetime

from newsdock_api.domain.records import (
    ArticleDetail,
    ArticleSummary,
    ArticleSummaryTone,
    FeedPage,
    FeedPageTone,
    NewArticlesPage,
    SemanticHit,
    SemanticResult,
    dump_page,
)

WHEN = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

# The keys of an article in every default response before this feature.
GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count",
}  # fmt: skip
TONE = {"tone", "tone_pos", "tone_neg", "tone_polarity"}


def _summary(**tone: float | None) -> ArticleSummary:
    return ArticleSummary(
        article_id="a", title="t", url="https://x/a", domain="x", published_at=WHEN,
        themes=["ECON_RATES"], seq=7, **tone,
    )  # fmt: skip


def _full() -> ArticleSummary:
    return _summary(tone=-4.0, tone_pos=1.5, tone_neg=9.5, tone_polarity=11.0)


def test_default_dump_has_exactly_the_golden_keys_even_with_tone_filled() -> None:
    summary = _full()
    assert set(summary.model_dump(mode="json")) == GOLDEN
    assert set(summary.to_json(())) == GOLDEN
    assert set(summary.to_json()) == GOLDEN
    assert set(summary.model_dump()) == GOLDEN


def test_include_adds_only_the_requested_keys() -> None:
    out = _full().to_json(("tone_neg",))
    assert set(out) == GOLDEN | {"tone_neg"}
    assert out["tone_neg"] == 9.5
    both = _full().to_json(("tone", "tone_neg"))
    assert set(both) == GOLDEN | {"tone", "tone_neg"}
    assert (both["tone"], both["tone_neg"]) == (-4.0, 9.5)


def test_requested_without_a_value_is_null_and_unrequested_is_absent() -> None:
    empty = _summary()
    asked = empty.to_json(("tone", "tone_neg"))
    assert asked["tone"] is None and asked["tone_neg"] is None
    assert set(asked) == GOLDEN | {"tone", "tone_neg"}
    assert set(empty.to_json(())) == GOLDEN


def test_to_json_is_json_ready() -> None:
    out = _full().to_json(("tone_neg",))
    assert out["published_at"] == "2026-10-30T12:00:00Z"
    assert "seq" not in out


def test_semantic_hit_keeps_its_own_keys_and_takes_tone() -> None:
    hit = SemanticHit.model_validate(
        {**dict(_full()), "score": 0.5, "matched_by": ["vector"]}
    )  # the way SemanticService builds hits
    out = hit.to_json(("tone_neg",))
    assert set(out) == GOLDEN | {"score", "matched_by", "tone_neg"}
    assert out["tone_neg"] == 9.5
    assert set(hit.to_json(())) == GOLDEN | {"score", "matched_by"}


def test_dump_page_covers_all_three_page_shapes() -> None:
    new = NewArticlesPage(articles=[_full()], next_cursor="c1")
    out = dump_page(new, ("tone",))
    assert out["next_cursor"] == "c1"
    assert set(out["articles"][0]) == GOLDEN | {"tone"}

    feed = FeedPage(articles=[_full()], next_before="2026-10-30T12:00:00+00:00,a")
    out = dump_page(feed, ())
    assert out["next_before"] == "2026-10-30T12:00:00+00:00,a"
    assert set(out["articles"][0]) == GOLDEN

    hit = SemanticHit.model_validate(
        {**dict(_full()), "score": 0.5, "matched_by": ["keyword"]}
    )
    result = SemanticResult(articles=[hit], mode="hybrid", degraded=True)
    out = dump_page(result, ("tone_neg",))
    assert (out["mode"], out["degraded"]) == ("hybrid", True)
    assert set(out["articles"][0]) == GOLDEN | {"score", "matched_by", "tone_neg"}


def test_dump_page_of_an_empty_page() -> None:
    assert dump_page(NewArticlesPage(articles=[], next_cursor="c"), ("tone",)) == {
        "articles": [],
        "next_cursor": "c",
    }


def test_the_documentation_models_list_the_optional_keys() -> None:
    fields = set(ArticleSummaryTone.model_fields)
    assert TONE <= fields
    assert "articles" in FeedPageTone.model_fields
    schema = FeedPageTone.model_json_schema(mode="serialization")
    props = schema["$defs"]["ArticleSummaryTone"]["properties"]
    assert TONE <= set(props)
    assert "seq" not in props


def test_detail_carries_all_four_tone_numbers() -> None:
    detail = ArticleDetail(
        article_id="a", title="t", url="https://x/a", domain="x", published_at=WHEN,
        ingested_at=WHEN, slot="20261030120000", themes=[], persons=[], orgs=[],
        tone=-4.0, tone_pos=1.5, tone_neg=9.5, tone_polarity=11.0, word_count=300,
        analyses=[], sources=[], source_count=1,
    )  # fmt: skip
    dumped = detail.model_dump(mode="json")
    assert TONE <= set(dumped)
    assert (dumped["tone_pos"], dumped["tone_neg"], dumped["tone_polarity"]) == (
        1.5,
        9.5,
        11.0,
    )


def test_detail_tone_numbers_default_to_none_for_older_callers() -> None:
    detail = ArticleDetail(
        article_id="a", title="t", url="https://x/a", domain="x", published_at=WHEN,
        ingested_at=WHEN, slot="s", themes=[], persons=[], orgs=[], tone=None,
        word_count=None, analyses=[], sources=[], source_count=1,
    )  # fmt: skip
    assert detail.tone_pos is None and detail.tone_neg is None
