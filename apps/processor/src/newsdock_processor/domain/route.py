"""Pure routing decision: one raw message → clean, events, mentions or dlq.

Dispatch is on `message.kind` (ADR-0032); a message without `kind` is GKG.
"""

from dataclasses import dataclass

from newsdock_core.contracts import CleanArticle, CleanEvent, CleanMention, RawMessage
from newsdock_core.events import parse_event_row
from newsdock_core.gkg import parse_row
from newsdock_core.mentions import parse_mention_row


@dataclass(frozen=True)
class Routed:
    topic: str
    key: str
    value: str  # JSON


def route(
    message: RawMessage,
    clean_topic: str,
    dlq_topic: str,
    *,
    events_topic: str | None = None,
    mentions_topic: str | None = None,
) -> Routed:
    """Never raises on bad data: parse errors become dlq messages (AC-4, AC-3).

    A non-GKG kind without its topic is a wiring mistake and raises `ValueError`.
    """
    if message.kind == "events":
        if events_topic is None:
            raise ValueError("events message routed without an events topic")
        parsed_event = parse_event_row(
            slot=message.slot, row_no=message.row_no, line=message.line
        )
        if isinstance(parsed_event, CleanEvent):
            return Routed(
                topic=events_topic,
                key=str(parsed_event.event_id),
                value=parsed_event.model_dump_json(),
            )
        return _dlq(message, dlq_topic, parsed_event.model_dump_json())
    if message.kind == "mentions":
        if mentions_topic is None:
            raise ValueError("mentions message routed without a mentions topic")
        parsed_mention = parse_mention_row(
            slot=message.slot, row_no=message.row_no, line=message.line
        )
        if isinstance(parsed_mention, CleanMention):
            return Routed(
                topic=mentions_topic,
                key=f"{parsed_mention.event_id}:{parsed_mention.url_hash}",
                value=parsed_mention.model_dump_json(),
            )
        return _dlq(message, dlq_topic, parsed_mention.model_dump_json())
    parsed = parse_row(slot=message.slot, row_no=message.row_no, line=message.line)
    if isinstance(parsed, CleanArticle):
        return Routed(
            topic=clean_topic, key=parsed.url_hash, value=parsed.model_dump_json()
        )
    return _dlq(message, dlq_topic, parsed.model_dump_json())


def _dlq(message: RawMessage, dlq_topic: str, value: str) -> Routed:
    return Routed(topic=dlq_topic, key=f"{message.slot}:{message.row_no}", value=value)
