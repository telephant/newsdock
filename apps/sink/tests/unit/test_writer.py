"""TC-31: batch failure → row-by-row retry, poison → dlq bad_field, rest written."""

import json
from pathlib import Path

import pytest
from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
from newsdock_sink.domain.writer import (
    DbUnavailable,
    RowRejected,
    SinkItem,
    process_batch,
)

ROOT = Path(__file__).resolve().parents[4]
EXPECTED = ROOT / "packages" / "core" / "tests" / "fixtures" / "expected_articles.json"


def items(n: int = 5) -> list[SinkItem]:
    with EXPECTED.open() as f:
        arts = [CleanArticle.model_validate(a) for a in json.load(f)][:n]
    return [SinkItem(key=a.url_hash, value=a.model_dump_json().encode()) for a in arts]


class FakeWriter:
    def __init__(
        self,
        poison: frozenset[str] = frozenset(),
        batch_fails: bool = False,
        down: bool = False,
    ) -> None:
        self.poison, self.batch_fails, self.down = poison, batch_fails, down
        self.written: list[str] = []

    def insert_batch(self, articles: list[CleanArticle]) -> int:
        if self.down:
            raise DbUnavailable("connection refused")
        if self.batch_fails:
            raise RowRejected("NUL byte somewhere in the batch")
        self.written += [a.url_hash for a in articles]
        return len(articles)

    def insert_one(self, article: CleanArticle) -> int:
        if self.down:
            raise DbUnavailable("connection refused")
        if article.url_hash in self.poison:
            raise RowRejected("invalid byte sequence")
        self.written.append(article.url_hash)
        return 1


class FakeDlq:
    def __init__(self) -> None:
        self.sent: list[tuple[str, DlqMessage]] = []

    def send(self, key: str, message: DlqMessage) -> None:
        self.sent.append((key, message))


def test_happy_batch_writes_all_and_sends_nothing_to_dlq() -> None:
    writer, dlq = FakeWriter(), FakeDlq()
    result = process_batch(items(), writer, dlq)
    assert result.written == 5 and dlq.sent == []


def test_poison_row_goes_to_dlq_and_the_rest_are_written() -> None:
    batch = items()
    poison_key = batch[2].key
    writer = FakeWriter(poison=frozenset({poison_key}), batch_fails=True)
    dlq = FakeDlq()
    result = process_batch(batch, writer, dlq)
    assert result.written == 4
    (key, message) = dlq.sent[0]
    assert key == poison_key and message.reason == DlqReason.bad_field
    assert poison_key not in writer.written


def test_db_down_raises_so_offsets_are_not_committed() -> None:
    writer, dlq = FakeWriter(down=True), FakeDlq()
    with pytest.raises(DbUnavailable):
        process_batch(items(), writer, dlq)
    assert dlq.sent == []  # a transient outage is not a row error (R-1)


def test_unparseable_clean_message_goes_to_dlq() -> None:
    writer, dlq = FakeWriter(), FakeDlq()
    bad = SinkItem(key="k", value=b"{not json")
    result = process_batch([bad, *items(2)], writer, dlq)
    assert result.written == 2
    assert dlq.sent[0][1].reason == DlqReason.bad_field
