"""Kafka producer for the raw topic (default gkg.raw, set in config)."""

from confluent_kafka import Producer
from newsdock_core.contracts import RawMessage


class KafkaRawPublisher:
    def __init__(self, bootstrap_servers: str, *, topic: str) -> None:
        self._topic = topic
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})

    def publish(self, key: str, message: RawMessage) -> None:
        self._producer.produce(
            self._topic, key=key.encode(), value=message.model_dump_json().encode()
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()
