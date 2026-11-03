"""Kafka loop for the sink: consume the clean topics in batches, write, commit.

With a `gdelt_writer` the loop also reads the Events and Mentions topics (ADR-0032);
offsets are committed once, after all three kinds of rows in the batch are written.
"""

import logging
import time
from datetime import timedelta

from confluent_kafka import Consumer, Producer
from newsdock_core.contracts import DlqMessage

from newsdock_sink.config import Settings
from newsdock_sink.domain.gdelt import GdeltWriter, process_events, process_mentions
from newsdock_sink.domain.writer import (
    BatchResult,
    DbUnavailable,
    SinkItem,
    StoryWriter,
    process_batch,
)

logger = logging.getLogger(__name__)


class KafkaDlqSink:
    def __init__(self, producer: Producer, *, topic: str) -> None:
        self._producer = producer
        self._topic = topic

    def send(self, key: str, message: DlqMessage) -> None:
        self._producer.produce(
            self._topic, key=key.encode(), value=message.model_dump_json().encode()
        )
        self._producer.poll(0)


class KafkaSinkLoop:
    def __init__(
        self,
        settings: Settings,
        writer: StoryWriter,
        *,
        group_id: str | None = None,
        gdelt_writer: GdeltWriter | None = None,
    ) -> None:
        self._settings = settings
        self._writer = writer
        self._gdelt_writer = gdelt_writer
        self._consumer = Consumer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": group_id or settings.kafka_group_id,
            "auto.offset.reset": settings.kafka_auto_offset_reset,
            "enable.auto.commit": False,  # invariant: manual commit after write,
        })  # fmt: skip
        topics = [settings.kafka_topics_clean]
        if gdelt_writer is not None:
            topics += [
                settings.kafka_topics_events_clean,
                settings.kafka_topics_mentions_clean,
            ]
        self._consumer.subscribe(topics)
        self._producer = Producer(
            {"bootstrap.servers": settings.kafka_bootstrap_servers}
        )
        self._dlq = KafkaDlqSink(self._producer, topic=settings.kafka_topics_dlq)

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
            items.append(
                SinkItem(
                    key=(key or b"").decode(),
                    value=value or b"",
                    topic=msg.topic() or "",
                )
            )
        if not items:
            return None
        events_topic = self._settings.kafka_topics_events_clean
        mentions_topic = self._settings.kafka_topics_mentions_clean
        articles = [i for i in items if i.topic not in (events_topic, mentions_topic)]
        events = [i for i in items if i.topic == events_topic]
        mentions = [i for i in items if i.topic == mentions_topic]
        try:
            result = BatchResult(canonicals=0, grouped=0, url_duplicates=0, dlq=0)
            if articles:
                result = process_batch(
                    articles,
                    self._writer,
                    self._dlq,
                    window=timedelta(hours=self._settings.story_window_hours),
                )
            if self._gdelt_writer is not None:
                if events:
                    process_events(events, self._gdelt_writer, self._dlq)
                if mentions:
                    process_mentions(mentions, self._gdelt_writer, self._dlq)
        except DbUnavailable as exc:  # no commit: redelivered after backoff (R-1)
            logger.warning("database unavailable, backing off: %s", exc)
            time.sleep(self._settings.db_backoff_seconds)
            return None
        self._producer.flush()
        self._consumer.commit()
        return result

    def close(self) -> None:
        self._consumer.close()
