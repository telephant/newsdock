"""Sink batches for Events and Mentions (M3c events-mentions, ADR-0032/0033).

One batch becomes one upsert. Duplicate keys inside the batch are collapsed first
(Postgres refuses an `ON CONFLICT DO UPDATE` that touches one row twice), keeping the
newest row: the event with the latest `date_added`, the mention with the latest
`mention_time`. A batch Postgres rejects is retried row by row so only the poison row
goes to the dead-letter topic as `bad_field`. A connection-level failure raises
`DbUnavailable`, so the caller backs off without committing offsets.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from newsdock_core.contracts import (
    CleanEvent,
    CleanMention,
    DlqMessage,
    DlqReason,
    Kind,
)
from pydantic import BaseModel, ValidationError

from newsdock_sink.domain.writer import DlqSink, RowRejected, SinkItem

logger = logging.getLogger(__name__)


class GdeltWriter(Protocol):
    """Upserts return how many rows were inserted or changed."""

    def upsert_events(self, events: list[CleanEvent]) -> int: ...

    def upsert_mentions(self, mentions: list[CleanMention]) -> int: ...


@dataclass(frozen=True)
class GdeltBatchResult:
    written: int  # rows inserted or changed (a replay of known rows is 0)
    collapsed: int  # duplicates inside the batch merged into the newest row
    dlq: int  # invalid payloads and rows Postgres rejected


def process_events(
    items: list[SinkItem], writer: GdeltWriter, dlq: DlqSink
) -> GdeltBatchResult:
    """Write one batch of events. Raises DbUnavailable; never raises on bad rows."""
    return _process(
        items,
        dlq,
        kind="events",
        model=CleanEvent,
        key_of=lambda e: str(e.event_id),
        newer=lambda a, b: a.date_added >= b.date_added,
        upsert=writer.upsert_events,
    )


def process_mentions(
    items: list[SinkItem], writer: GdeltWriter, dlq: DlqSink
) -> GdeltBatchResult:
    """Write one batch of mentions. Raises DbUnavailable; never raises on bad rows."""
    return _process(
        items,
        dlq,
        kind="mentions",
        model=CleanMention,
        key_of=lambda m: f"{m.event_id}:{m.url_hash}",
        newer=lambda a, b: a.mention_time >= b.mention_time,
        upsert=writer.upsert_mentions,
    )


def _process[M: BaseModel](
    items: list[SinkItem],
    dlq: DlqSink,
    *,
    kind: Kind,
    model: type[M],
    key_of: Callable[[M], str],
    newer: Callable[[M, M], bool],
    upsert: Callable[[list[M]], int],
) -> GdeltBatchResult:
    dlq_count = collapsed = 0
    kept: dict[str, tuple[str, M]] = {}  # row key -> (kafka key, newest row)

    def reject(kafka_key: str, line: str) -> None:
        dlq.send(
            kafka_key,
            DlqMessage(
                reason=DlqReason.bad_field,
                slot="unknown",
                row_no=-1,
                line=line,
                kind=kind,
            ),
        )

    for item in items:
        try:
            row = model.model_validate_json(item.value)
        except ValidationError:
            reject(item.key, item.value.decode("utf-8", errors="replace"))
            dlq_count += 1
            continue
        row_key = key_of(row)
        current = kept.get(row_key)
        if current is None:
            kept[row_key] = (item.key, row)
            continue
        collapsed += 1
        if newer(row, current[1]):
            kept[row_key] = (item.key, row)

    if not kept:
        return GdeltBatchResult(written=0, collapsed=collapsed, dlq=dlq_count)

    rows = [row for _, row in kept.values()]
    try:
        written = upsert(rows)
    except RowRejected as exc:
        logger.warning("%s batch rejected (%s); retrying row by row", kind, exc)
        written = 0
        for kafka_key, row in kept.values():
            try:
                written += upsert([row])
            except RowRejected as row_exc:
                logger.warning("%s row %s rejected: %s", kind, kafka_key, row_exc)
                reject(kafka_key, row.model_dump_json())
                dlq_count += 1
    result = GdeltBatchResult(written=written, collapsed=collapsed, dlq=dlq_count)
    logger.info(
        "%s: %d written, %d collapsed duplicates, %d dlq",
        kind,
        result.written,
        result.collapsed,
        result.dlq,
    )
    return result
