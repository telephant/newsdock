"""TC-10, TC-11 (domain half) and the poison fallback: Events and Mentions batches."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from newsdock_core.contracts import CleanEvent, CleanMention, DlqMessage
from newsdock_core.events import parse_event_row
from newsdock_core.mentions import parse_mention_row
from newsdock_sink.domain.gdelt import process_events, process_mentions
from newsdock_sink.domain.writer import DbUnavailable, RowRejected, SinkItem

FIXTURES = Path(__file__).resolve().parents[4] / "packages/core/tests/fixtures"
SLOT = "20261102110000"


def event(row: int = 0, **changes: object) -> CleanEvent:
    line = (FIXTURES / "events_sample.tsv").read_text().splitlines()[row]
    parsed = parse_event_row(slot=SLOT, row_no=row, line=line)
    assert isinstance(parsed, CleanEvent)
    return parsed.model_copy(update=changes)


def mention(row: int = 0, **changes: object) -> CleanMention:
    line = (FIXTURES / "mentions_sample.tsv").read_text().splitlines()[row]
    parsed = parse_mention_row(slot=SLOT, row_no=row, line=line)
    assert isinstance(parsed, CleanMention)
    return parsed.model_copy(update=changes)


def item(model: CleanEvent | CleanMention, key: str = "k") -> SinkItem:
    return SinkItem(key=key, value=model.model_dump_json().encode())


class FakeWriter:
    def __init__(self, *, reject_ids: set[int] | None = None, down: bool = False):
        self.event_calls: list[list[CleanEvent]] = []
        self.mention_calls: list[list[CleanMention]] = []
        self.link_calls: list[list[CleanMention]] = []
        self._reject = reject_ids or set()
        self._down = down

    def upsert_events(self, events: list[CleanEvent]) -> int:
        if self._down:
            raise DbUnavailable("down")
        self.event_calls.append(list(events))
        if any(e.event_id in self._reject for e in events):
            raise RowRejected("bad value")
        return len(events)

    def upsert_mentions(self, mentions: list[CleanMention]) -> int:
        if self._down:
            raise DbUnavailable("down")
        self.mention_calls.append(list(mentions))
        if any(m.event_id in self._reject for m in mentions):
            raise RowRejected("bad value")
        return len(mentions)

    def link_copy_mentions(self, mentions: list[CleanMention]) -> None:
        if self._down:
            raise DbUnavailable("down")
        self.link_calls.append(list(mentions))


class FakeDlq:
    def __init__(self) -> None:
        self.sent: list[tuple[str, DlqMessage]] = []

    def send(self, key: str, message: DlqMessage) -> None:
        self.sent.append((key, message))


# TC-10: the same key twice in one batch is written once
def test_duplicate_events_in_a_batch_are_collapsed_to_the_newest() -> None:
    older = event(0, num_mentions=3, date_added=datetime(2026, 11, 2, 11, tzinfo=UTC))
    newer = older.model_copy(
        update={"num_mentions": 7, "date_added": datetime(2026, 11, 2, 12, tzinfo=UTC)}
    )
    writer, dlq = FakeWriter(), FakeDlq()
    result = process_events([item(newer), item(older)], writer, dlq)
    assert len(writer.event_calls) == 1 and len(writer.event_calls[0]) == 1
    assert writer.event_calls[0][0].num_mentions == 7  # newest wins, not last seen
    assert (result.written, result.collapsed, result.dlq) == (1, 1, 0)
    assert dlq.sent == []


def test_duplicate_mentions_in_a_batch_are_collapsed() -> None:
    first, second = mention(0), mention(1)  # the repeated (event, URL) pair
    assert (first.event_id, first.url_hash) == (second.event_id, second.url_hash)
    writer, dlq = FakeWriter(), FakeDlq()
    result = process_mentions([item(first), item(second)], writer, dlq)
    assert len(writer.mention_calls[0]) == 1
    assert (result.written, result.collapsed) == (1, 1)


def test_distinct_rows_are_all_written_in_one_call() -> None:
    writer, dlq = FakeWriter(), FakeDlq()
    items = [item(event(n)) for n in range(5)]
    result = process_events(items, writer, dlq)
    assert len(writer.event_calls) == 1 and len(writer.event_calls[0]) == 5
    assert result.written == 5 and result.collapsed == 0


# invalid payloads are dead-lettered with their kind and never reach the writer
def test_invalid_payload_goes_to_the_dlq_with_its_kind() -> None:
    writer, dlq = FakeWriter(), FakeDlq()
    bad = SinkItem(key="k9", value=b'{"event_id": "not a number"}')
    result = process_events([bad, item(event(0))], writer, dlq)
    assert result.dlq == 1 and result.written == 1
    key, message = dlq.sent[0]
    assert key == "k9" and message.kind == "events" and message.reason == "bad_field"
    result = process_mentions([bad], writer, dlq)
    assert dlq.sent[1][1].kind == "mentions" and result.dlq == 1


# a batch Postgres rejects is retried row by row; only the poison row is dead-lettered
def test_rejected_batch_falls_back_to_row_by_row() -> None:
    good, poison = event(0), event(1)
    writer = FakeWriter(reject_ids={poison.event_id})
    dlq = FakeDlq()
    result = process_events([item(good), item(poison, "kp")], writer, dlq)
    assert (result.written, result.dlq) == (1, 1)
    assert [m.kind for _, m in dlq.sent] == ["events"]
    assert dlq.sent[0][0] == "kp"
    assert len(writer.event_calls) == 1 + 2  # the batch, then one call per row


def test_db_outage_propagates_so_the_caller_does_not_commit() -> None:
    with pytest.raises(DbUnavailable):
        process_events([item(event(0))], FakeWriter(down=True), FakeDlq())
    with pytest.raises(DbUnavailable):
        process_mentions([item(mention(0))], FakeWriter(down=True), FakeDlq())


def test_empty_batch_does_not_touch_the_writer() -> None:
    writer = FakeWriter()
    assert process_events([], writer, FakeDlq()).written == 0
    assert writer.event_calls == [] and writer.mention_calls == []


def test_mentions_are_linked_once_after_the_upsert() -> None:  # TC-9 (mention path)
    writer, dlq = FakeWriter(), FakeDlq()
    rows = [mention(0), mention(1)]

    process_mentions([item(m, key=str(i)) for i, m in enumerate(rows)], writer, dlq)

    assert len(writer.mention_calls) == 1 and len(writer.link_calls) == 1
    assert {m.url_hash for m in writer.link_calls[0]} == {m.url_hash for m in rows}


def test_no_link_when_the_database_is_down_or_the_batch_is_empty() -> None:  # TC-9
    down = FakeWriter(down=True)
    with pytest.raises(DbUnavailable):
        process_mentions([item(mention(0))], down, FakeDlq())
    assert down.link_calls == []

    quiet = FakeWriter()
    process_mentions([], quiet, FakeDlq())
    assert quiet.link_calls == []
