"""Pure routing decision: one raw message → clean or dlq (design-detail §2)."""

from dataclasses import dataclass

from newsdock_core.contracts import CleanArticle, RawMessage
from newsdock_core.gkg import parse_row

CLEAN_TOPIC = "gkg.clean"
DLQ_TOPIC = "gkg.dlq"


@dataclass(frozen=True)
class Routed:
    topic: str
    key: str
    value: str  # JSON


def route(message: RawMessage) -> Routed:
    """Never raises: parse errors become dlq messages (AC-4)."""
    parsed = parse_row(slot=message.slot, row_no=message.row_no, line=message.line)
    if isinstance(parsed, CleanArticle):
        return Routed(
            topic=CLEAN_TOPIC, key=parsed.url_hash, value=parsed.model_dump_json()
        )
    return Routed(
        topic=DLQ_TOPIC,
        key=f"{message.slot}:{message.row_no}",
        value=parsed.model_dump_json(),
    )
