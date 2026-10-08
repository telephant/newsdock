"""TC-9 (sink half): the sink subscribes to and dead-letters on configured topics."""

from typing import Any

import pytest
from newsdock_core.contracts import DlqMessage, DlqReason
from newsdock_sink.adapters import kafka as adapter
from newsdock_sink.config import Settings


class FakeConsumer:
    instances: list["FakeConsumer"] = []

    def __init__(self, conf: dict[str, Any]) -> None:
        self.conf = conf
        self.subscribed: list[str] = []
        FakeConsumer.instances.append(self)

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = topics


class FakeProducer:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.produced: list[str] = []

    def produce(self, topic: str, key: bytes, value: bytes) -> None:
        self.produced.append(topic)

    def poll(self, timeout: float) -> None:
        pass


class NoWriter:
    pass


def test_consumer_uses_configured_topic_group_and_offset_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter, "Consumer", FakeConsumer)
    monkeypatch.setattr(adapter, "Producer", FakeProducer)
    settings = Settings(
        kafka_topics_clean="clean.test",
        kafka_group_id="sink-2",
        kafka_auto_offset_reset="latest",
    )
    adapter.KafkaSinkLoop(settings, NoWriter())  # type: ignore[arg-type]
    consumer = FakeConsumer.instances[-1]
    assert consumer.subscribed == ["clean.test"]
    assert consumer.conf["group.id"] == "sink-2"
    assert consumer.conf["auto.offset.reset"] == "latest"
    assert consumer.conf["enable.auto.commit"] is False  # invariant stays in code


def test_dlq_messages_go_to_the_configured_topic() -> None:
    producer = FakeProducer({})
    sink = adapter.KafkaDlqSink(producer, topic="dlq.test")  # type: ignore[arg-type]
    sink.send("k", DlqMessage(reason=DlqReason.bad_field, slot="s", row_no=1, line="x"))
    assert producer.produced == ["dlq.test"]
