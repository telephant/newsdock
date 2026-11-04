"""TC-17, TC-19, TC-20 (domain part): `events` joins the tone names in `include`."""

from datetime import UTC, date, datetime

import pytest
from newsdock_api.domain import tone
from newsdock_api.domain.include import (
    INCLUDE_NAMES,
    TONE_FIELDS,
    InvalidInclude,
    parse_include,
)
from newsdock_api.domain.records import (
    ArticleDetail,
    ArticleSummary,
    EventActor,
    EventLocation,
    EventOut,
    FeedPage,
    dump_page,
)

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def summary(**changes: object) -> ArticleSummary:
    base: dict[str, object] = {
        "article_id": "h1",
        "title": "t",
        "url": "https://e.com/a",
        "domain": "e.com",
        "published_at": NOW,
        "themes": [],
        "seq": 1,
    }
    return ArticleSummary(**(base | changes))


def event(event_id: int = 7, **changes: object) -> EventOut:
    base: dict[str, object] = {
        "event_id": event_id,
        "date": date(2026, 11, 2),
        "cameo_code": "040",
        "cameo_root": "04",
        "goldstein": 1.0,
        "quad_class": 1,
        "num_mentions": 5,
        "num_sources": 1,
        "avg_tone": -2.5,
        "actor1": EventActor(),
        "actor2": EventActor(code="GOV", name="PRESIDENT", type="GOV"),
        "location": EventLocation(name="Paris", country="FR", lat=48.8, lon=2.3),
        "source_url": "https://e.com/a",
        "mention_count": 9,
    }
    return EventOut(**(base | changes))


def test_include_names_are_the_tone_fields_plus_events_and_body() -> None:
    assert TONE_FIELDS == ("tone", "tone_pos", "tone_neg", "tone_polarity")
    assert INCLUDE_NAMES == (*TONE_FIELDS, "events", "body")


def test_tone_module_still_exports_the_same_rules() -> None:
    assert tone.parse_include is parse_include
    assert tone.InvalidInclude is InvalidInclude
    assert tone.TONE_FIELDS == TONE_FIELDS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("events", ("events",)),
        (["events"], ("events",)),
        ("tone, events,events", ("tone", "events")),
        (["events", "tone_neg", "events"], ("events", "tone_neg")),
        (None, ()),
        ("", ()),
    ],
)
def test_events_is_accepted_like_a_tone_name(
    raw: object, expected: tuple[str, ...]
) -> None:
    assert parse_include(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["bogus", "events,bogus", ["events", "Events"], [1]])
def test_unknown_names_are_rejected_with_events_in_the_message(raw: object) -> None:
    with pytest.raises(InvalidInclude) as raised:
        parse_include(raw)  # type: ignore[arg-type]
    assert "events" in str(raised.value) or raw == [1]


# TC-17: without `events` asked for, nothing about events appears
def test_default_dumps_never_carry_events() -> None:
    plain = summary(events=[event()])
    assert "events" not in plain.model_dump(mode="json")
    assert "events" not in plain.to_json()
    assert "events" not in plain.to_json(["tone"])


def test_to_json_writes_events_when_asked() -> None:
    out = summary(events=[event(7), event(8)]).to_json(["events"])
    assert [e["event_id"] for e in out["events"]] == [7, 8]
    first = out["events"][0]
    assert first["date"] == "2026-11-02" and first["mention_count"] == 9
    assert first["actor2"] == {
        "code": "GOV",
        "name": "PRESIDENT",
        "country": None,
        "type": "GOV",
    }
    assert first["location"]["name"] == "Paris"
    assert set(first) == {
        "event_id", "date", "cameo_code", "cameo_root", "goldstein", "quad_class",
        "num_mentions", "num_sources", "avg_tone", "actor1", "actor2", "location",
        "source_url", "mention_count",
    }  # fmt: skip


# TC-19: asked for, but none stored, is an empty list
def test_events_is_an_empty_list_when_the_article_has_none() -> None:
    assert summary().to_json(["events"])["events"] == []
    assert summary(events=[]).to_json(["events"])["events"] == []


def test_location_may_be_null() -> None:
    out = summary(events=[event(location=None)]).to_json(["events"])
    assert out["events"][0]["location"] is None


def test_tone_and_events_can_be_asked_together() -> None:
    out = summary(tone=-1.0, events=[event()]).to_json(["tone", "events"])
    assert out["tone"] == -1.0 and len(out["events"]) == 1


def test_dump_page_adds_events_on_every_article() -> None:
    page = FeedPage(articles=[summary(events=[event()]), summary()], next_before=None)
    out = dump_page(page, ["events"])
    assert [len(a["events"]) for a in out["articles"]] == [1, 0]
    assert out["next_before"] is None
    assert all("events" not in a for a in dump_page(page)["articles"])


def test_detail_always_carries_events() -> None:
    detail = ArticleDetail(
        article_id="h1", title="t", url="u", domain=None, published_at=NOW,
        ingested_at=NOW, slot="s", themes=[], persons=[], orgs=[], tone=None,
        word_count=None, analyses=[], sources=[], source_count=1,
    )  # fmt: skip
    assert detail.model_dump(mode="json")["events"] == []
    with_events = detail.model_copy(update={"events": [event()]})
    assert len(with_events.model_dump(mode="json")["events"]) == 1
