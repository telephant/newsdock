"""Kafka loop for the sink: consume gkg.clean in batches, write, commit."""

import logging
import time
from datetime import timedelta

from confluent_kafka import Consumer, Producer
from newsdock_core.contracts import DlqMessage

from newsdock_sink.config import Settings
from newsdock_sink.domain.writer import (
    BatchResult,
    DbUnavailable,
    SinkItem,
    StoryWriter,
    process_batch,
)

logger = logging.getLogger(__name__)

CLEAN_TOPIC = "gkg.clean"
DLQ_TOPIC = "gkg.dlq"


class KafkaDlqSink:
    def __init__(self, producer: Producer) -> None:
        self._producer = producer

    def send(self, key: str, message: DlqMessage) -> None:
        self._producer.produce(
            DLQ_TOPIC, key=key.encode(), value=message.model_dump_json().encode()
        )
        self._producer.poll(0)


class KafkaSinkLoop:
    def __init__(
        self, settings: Settings, writer: StoryWriter, *, group_id: str = "sink"
    ) -> None:
        self._settings = settings
        self._writer = writer
        self._consumer = Consumer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })  # fmt: skip
        self._consumer.subscribe([CLEAN_TOPIC])
        self._producer = Producer(
            {"bootstrap.servers": settings.kafka_bootstrap_servers}
        )
        self._dlq = KafkaDlqSink(self._producer)

    def run_once(self) -> BatchResult | None:
        """Consume up to batch_size/1 s, write, flush dlq, commit offsets."""
        items: list[SinkItem] = []
        deadline = time.monotonic() + self._settings.batch_window_seconds
        while len(items) < self._settings.batch_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            msg = self._consumer.poll(remaining)
            if msg is None or msg.error() is not None:
                if msg is not None:
                    logger.error("consumer error: %s", msg.error())
                break
            key, value = msg.key(), msg.value()
            items.append(SinkItem(key=(key or b"").decode(), value=value or b""))
        if not items:
            return None
        try:
            result = process_batch(
                items,
                self._writer,
                self._dlq,
                window=timedelta(hours=self._settings.story_window_hours),
            )
        except DbUnavailable as exc:  # no commit: redelivered after backoff (R-1)
            logger.warning("database unavailable, backing off: %s", exc)
            time.sleep(self._settings.db_backoff_seconds)
            return None
        self._producer.flush()
        self._consumer.commit()
        return result

    def close(self) -> None:
        self._consumer.close()
