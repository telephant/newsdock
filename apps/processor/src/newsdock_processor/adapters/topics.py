"""Create the configured Kafka topics; idempotent. Run: python -m ...adapters.topics."""

import logging
from typing import Any

from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from newsdock_config import load_settings

from newsdock_processor.config import Settings

logger = logging.getLogger(__name__)


def ensure_topics(
    settings: Settings, *, admin: Any = None, timeout_seconds: float = 30.0
) -> list[str]:
    """Create the configured topics that do not exist yet; return the new ones."""
    admin = admin or AdminClient(
        {"bootstrap.servers": settings.kafka_bootstrap_servers}
    )
    existing = set(admin.list_topics(timeout=timeout_seconds).topics)
    wanted = [
        settings.kafka_topics_raw,
        settings.kafka_topics_clean,
        settings.kafka_topics_dlq,
    ]
    missing = [name for name in wanted if name not in existing]
    if not missing:
        return []
    futures = admin.create_topics([
        NewTopic(
            name,
            num_partitions=settings.kafka_topic_partitions,
            replication_factor=settings.kafka_topic_replication_factor,
        )
        for name in missing
    ])  # fmt: skip
    for name, future in futures.items():
        try:
            future.result()
        except KafkaException as exc:
            if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
        logger.info("topic %s ready", name)
    return missing


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    created = ensure_topics(settings)
    logging.getLogger(__name__).info("topics ensured (created: %s)", created or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
