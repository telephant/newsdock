"""TC-6 (AC-3, ADR-0032): routing dispatches on the message kind."""

import json
from pathlib import Path
from typing import Any

import pytest
from newsdock_core.contracts import RawMessage
from newsdock_processor.domain.route import route

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
SLOT = "20261102110000"
TOPICS: dict[str, Any] = {
    "clean_topic": "c.test",
    "dlq_topic": "d.test",
    "events_topic": "e.test",
    "mentions_topic": "m.test",
}


def _line(name: str, row: int = 0) -> str:
    return (FIXTURES / name).read_text().splitlines()[row]


def _route(message: RawMessage) -> Any:
    return route(
        message,
        TOPICS["clean_topic"],
        TOPICS["dlq_topic"],
        events_topic=TOPICS["events_topic"],
        mentions_topic=TOPICS["mentions_topic"],
    )


def test_gkg_still_routes_to_clean_keyed_by_url_hash() -> None:
    line = _line("gkg_sample.tsv")
    routed = _route(RawMessage(slot="20261004081500", row_no=0, line=line))
    assert routed.topic == "c.test"
    assert routed.key == json.loads(routed.value)["url_hash"]


def test_message_without_kind_is_gkg() -> None:
    message = RawMessage.model_validate_json(
        json.dumps(
            {"slot": "20261004081500", "row_no": 0, "line": _line("gkg_sample.tsv")}
        )
    )
    assert _route(message).topic == "c.test"


def test_event_routes_to_events_topic_keyed_by_event_id() -> None:
    line = _line("events_sample.tsv")
    routed = _route(RawMessage(slot=SLOT, row_no=0, line=line, kind="events"))
    assert routed.topic == "e.test"
    assert routed.key == "1331041275"
    assert json.loads(routed.value)["event_id"] == 1331041275


def test_mention_routes_to_mentions_topic_keyed_by_event_and_url_hash() -> None:
    line = _line("mentions_sample.tsv")
    routed = _route(RawMessage(slot=SLOT, row_no=0, line=line, kind="mentions"))
    payload = json.loads(routed.value)
    assert routed.topic == "m.test"
    assert routed.key == f"{payload['event_id']}:{payload['url_hash']}"


@pytest.mark.parametrize(
    ("kind", "file"),
    [("events", "bad_event_rows.json"), ("mentions", "bad_mention_rows.json")],
)
def test_bad_rows_go_to_the_shared_dlq_with_their_kind(kind: str, file: str) -> None:
    cases = json.loads((FIXTURES / file).read_text())
    for number, case in enumerate(cases):
        routed = _route(
            RawMessage(slot=SLOT, row_no=number, line=case["line"], kind=kind)
        )
        payload = json.loads(routed.value)
        assert routed.topic == "d.test"
        assert routed.key == f"{SLOT}:{number}"
        assert payload["reason"] == case["expect"]
        assert payload["kind"] == kind


def test_non_gkg_kind_without_its_topic_fails_fast() -> None:
    message = RawMessage(
        slot=SLOT, row_no=0, line=_line("events_sample.tsv"), kind="events"
    )
    with pytest.raises(ValueError, match="events"):
        route(message, "c.test", "d.test")
