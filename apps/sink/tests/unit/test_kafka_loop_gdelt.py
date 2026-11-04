"""TC-9 (sink half): the loop reads three topics and routes messages by topic."""

from pathlib import Path
from typing import Any

import pytest
from newsdock_core.contracts import CleanEvent, CleanMention
from newsdock_core.events import parse_event_row
from newsdock_core.mentions import parse_mention_row
from newsdock_sink.adapters import kafka as adapter
from newsdock_sink.config import Settings
from newsdock_sink.domain.writer import DbUnavailable

FIXTURES = Path(__file__).resolve().parents[4] / "packages/core/tests/fixtures"


class Msg:
    def __init__(self, topic: str, key: str, value: bytes) -> None:
        self._topic, self._key, self._value = topic, key, value

    def topic(self) -> str:
        return self._topic

    def key(self) -> bytes:
        return self._key.encode()

    def value(self) -> bytes:
        return self._value

    def error(self) -> None:
        return None


class QueueConsumer:
    instances: list["QueueConsumer"] = []
    queue: list[Msg] = []
    commits = 0

    def __init__(self, conf: dict[str, Any]) -> None:
        self.conf = conf
        self.subscribed: list[str] = []
        QueueConsumer.instances.append(self)

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = topics

    def poll(self, timeout: float) -> Msg | None:
        return QueueConsumer.queue.pop(0) if QueueConsumer.queue else None

    def commit(self) -> None:
        QueueConsumer.commits += 1


class FakeProducer:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.produced: list[str] = []

    def produce(self, topic: str, key: bytes, value: bytes) -> None:
        self.produced.append(topic)

    def poll(self, timeout: float) -> None:
        pass

    def flush(self) -> None:
        pass


class NoArticleWriter:
    """Article items must not reach it in these tests."""


class GdeltRecorder:
    def __init__(self, *, down: bool = False) -> None:
        self.events: list[CleanEvent] = []
        self.mentions: list[CleanMention] = []
        self._down = down

    def upsert_events(self, events: list[CleanEvent]) -> int:
        if self._down:
            raise DbUnavailable("down")
        self.events.extend(events)
        return len(events)

    def upsert_mentions(self, mentions: list[CleanMention]) -> int:
        if self._down:
            raise DbUnavailable("down")
        self.mentions.extend(mentions)
        return len(mentions)

    def link_copy_mentions(self, mentions: list[CleanMention]) -> None:
        pass


def _payloads() -> tuple[bytes, bytes]:
    ev = parse_event_row(
        slot="s",
        row_no=0,
        line=(FIXTURES / "events_sample.tsv").read_text().splitlines()[0],
    )
    mn = parse_mention_row(
        slot="s",
        row_no=0,
        line=(FIXTURES / "mentions_sample.tsv").read_text().splitlines()[0],
    )
    assert isinstance(ev, CleanEvent) and isinstance(mn, CleanMention)
    return ev.model_dump_json().encode(), mn.model_dump_json().encode()


def _loop(
    monkeypatch: pytest.MonkeyPatch, writer: GdeltRecorder | None
) -> adapter.KafkaSinkLoop:
    monkeypatch.setattr(adapter, "Consumer", QueueConsumer)
    monkeypatch.setattr(adapter, "Producer", FakeProducer)
    monkeypatch.setattr("newsdock_sink.adapters.kafka.time.sleep", lambda _s: None)
    QueueConsumer.queue, QueueConsumer.commits = [], 0
    settings = Settings(
        kafka_topics_clean="c.test",
        kafka_topics_events_clean="e.test",
        kafka_topics_mentions_clean="m.test",
        batch_window_seconds=0.5,
    )
    return adapter.KafkaSinkLoop(
        settings,
        NoArticleWriter(),  # type: ignore[arg-type]
        gdelt_writer=writer,
    )


def test_sink_subscribes_to_three_topics_only_with_a_gdelt_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _loop(monkeypatch, GdeltRecorder())
    assert QueueConsumer.instances[-1].subscribed == ["c.test", "e.test", "m.test"]
    _loop(monkeypatch, None)
    assert QueueConsumer.instances[-1].subscribed == ["c.test"]


def test_run_once_routes_messages_by_topic_and_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = GdeltRecorder()
    loop = _loop(monkeypatch, writer)
    event_json, mention_json = _payloads()
    QueueConsumer.queue = [
        Msg("e.test", "1331041275", event_json),
        Msg("m.test", "1331000341:h", mention_json),
    ]
    assert loop.run_once() is not None
    assert len(writer.events) == 1 and len(writer.mentions) == 1
    assert QueueConsumer.commits == 1


def test_db_outage_on_gdelt_rows_means_no_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = _loop(monkeypatch, GdeltRecorder(down=True))
    event_json, _ = _payloads()
    QueueConsumer.queue = [Msg("e.test", "1331041275", event_json)]
    assert loop.run_once() is None
    assert QueueConsumer.commits == 0
