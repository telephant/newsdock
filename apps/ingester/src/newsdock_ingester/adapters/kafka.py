"""Kafka producer for gkg.raw."""

from confluent_kafka import Producer
from newsdock_core.contracts import RawMessage

RAW_TOPIC = "gkg.raw"


class KafkaRawPublisher:
    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})

    def publish(self, key: str, message: RawMessage) -> None:
        self._producer.produce(
            RAW_TOPIC, key=key.encode(), value=message.model_dump_json().encode()
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()
