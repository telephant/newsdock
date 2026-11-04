"""ADR-0032: `kind` is additive; messages without it still mean GKG."""

from newsdock_core.contracts import DlqMessage, DlqReason, RawMessage


def test_raw_message_without_kind_is_gkg() -> None:
    msg = RawMessage.model_validate_json('{"slot": "s", "row_no": 1, "line": "x"}')
    assert msg.kind == "gkg"


def test_raw_message_round_trips_kind() -> None:
    msg = RawMessage(slot="s", row_no=1, line="x", kind="events")
    assert RawMessage.model_validate_json(msg.model_dump_json()).kind == "events"


def test_dlq_message_defaults_to_gkg_and_has_the_new_reason() -> None:
    dlq = DlqMessage(reason=DlqReason.missing_event_id, slot="s", row_no=0, line="x")
    assert dlq.kind == "gkg"
    assert DlqReason("missing_event_id") is DlqReason.missing_event_id
    assert {r.value for r in DlqReason} >= {
        "missing_url",
        "missing_title",
        "bad_column_count",
        "bad_field",
    }
