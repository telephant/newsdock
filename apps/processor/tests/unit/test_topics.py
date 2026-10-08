"""TC-10 (unit half): the topic job creates only the missing configured topics."""

from concurrent.futures import Future
from types import SimpleNamespace
from typing import Any

from confluent_kafka import KafkaError, KafkaException
from newsdock_processor.adapters.topics import ensure_topics
from newsdock_processor.config import Settings


class FakeAdmin:
    def __init__(self, existing: set[str], fail_with: KafkaError | None = None) -> None:
        self.existing = existing
        self.created: list[Any] = []
        self._fail_with = fail_with

    def list_topics(self, timeout: float) -> Any:
        return SimpleNamespace(topics={t: object() for t in self.existing})

    def create_topics(self, new_topics: list[Any]) -> dict[str, Future[None]]:
        out: dict[str, Future[None]] = {}
        for nt in new_topics:
            self.created.append(nt)
            fut: Future[None] = Future()
            if self._fail_with is not None:
                fut.set_exception(KafkaException(self._fail_with))
            else:
                fut.set_result(None)
            out[nt.topic] = fut
        return out


def settings() -> Settings:
    return Settings(
        kafka_topics_raw="t.raw",
        kafka_topics_clean="t.clean",
        kafka_topics_dlq="t.dlq",
        kafka_topic_partitions=2,
        kafka_topic_replication_factor=1,
    )


def test_creates_all_three_configured_topics_with_configured_shape() -> None:
    admin = FakeAdmin(existing=set())
    created = ensure_topics(settings(), admin=admin)
    assert sorted(created) == ["t.clean", "t.dlq", "t.raw"]
    assert {nt.num_partitions for nt in admin.created} == {2}
    assert {nt.replication_factor for nt in admin.created} == {1}


def test_second_run_creates_nothing() -> None:
    admin = FakeAdmin(existing={"t.raw", "t.clean", "t.dlq", "__consumer_offsets"})
    assert ensure_topics(settings(), admin=admin) == []
    assert admin.created == []


def test_already_exists_race_is_tolerated() -> None:
    err = KafkaError(KafkaError.TOPIC_ALREADY_EXISTS)
    admin = FakeAdmin(existing=set(), fail_with=err)
    ensure_topics(settings(), admin=admin)  # must not raise
