"""Kafka consumer/producer loop: raw → clean / dlq (topic names from config).

Manual offset commits after flush (at-least-once; downstream is idempotent).
A message whose JSON envelope itself is broken goes to the dlq as `bad_field`.
"""

import logging

from confluent_kafka import Consumer, Producer
from newsdock_core.contracts import DlqMessage, DlqReason, RawMessage
from pydantic import ValidationError

from newsdock_processor.config import Settings
from newsdock_processor.domain.route import route

logger = logging.getLogger(__name__)


class KafkaProcessorLoop:
    def __init__(self, settings: Settings, *, group_id: str | None = None) -> None:
        self._settings = settings
        self._consumer = Consumer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": group_id or settings.kafka_group_id,
            "auto.offset.reset": settings.kafka_auto_offset_reset,
            "enable.auto.commit": False,  # invariant: manual commit after flush
        })  # fmt: skip
        self._consumer.subscribe([settings.kafka_topics_raw])
        self._producer = Producer(
            {"bootstrap.servers": settings.kafka_bootstrap_servers}
        )

    def run_once(self, *, max_messages: int, timeout_seconds: float) -> int:
        """Process up to max_messages; flush, then commit. Returns count."""
        processed = 0
        for _ in range(max_messages):
            msg = self._consumer.poll(timeout_seconds)
            if msg is None:
                break
            if msg.error() is not None:
                logger.error("consumer error: %s", msg.error())
                break
            value = msg.value()
            key = msg.key()
            try:
                raw = RawMessage.model_validate_json(value or b"")
                routed = route(
                    raw,
                    self._settings.kafka_topics_clean,
                    self._settings.kafka_topics_dlq,
                )
            except ValidationError:
                slot, _, row_no = (key or b"?:0").decode().partition(":")
                dlq = DlqMessage(
                    reason=DlqReason.bad_field,
                    slot=slot,
                    row_no=int(row_no) if row_no.isdigit() else -1,
                    line=(value or b"").decode("utf-8", errors="replace"),
                )
                routed_topic, routed_key, routed_value = (
                    self._settings.kafka_topics_dlq,
                    (key or b"?").decode(),
                    dlq.model_dump_json(),
                )
                self._producer.produce(
                    routed_topic,
                    key=routed_key.encode(),
                    value=routed_value.encode(),
                )
                self._producer.poll(0)
                processed += 1
                continue
            self._producer.produce(
                routed.topic, key=routed.key.encode(), value=routed.value.encode()
            )
            self._producer.poll(0)
            processed += 1
        if processed:
            self._producer.flush()
            self._consumer.commit()
        return processed

    def close(self) -> None:
        self._consumer.close()
