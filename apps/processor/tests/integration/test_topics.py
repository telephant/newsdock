"""TC-10: the topic job creates the configured topics on a real broker (Docker)."""

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from confluent_kafka.admin import AdminClient
from newsdock_processor.adapters.topics import ensure_topics
from newsdock_processor.config import Settings

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-topics-test"
BOOTSTRAP = "127.0.0.1:29092"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def kafka() -> Iterator[str]:
    assert _compose("up", "-d", "--wait", "kafka").returncode == 0
    yield BOOTSTRAP
    _compose("down", "-v", "--remove-orphans")


def test_topics_are_created_with_configured_partitions_and_are_idempotent(
    kafka: str,
) -> None:
    settings = Settings(
        kafka_bootstrap_servers=kafka,
        kafka_topics_raw="test.raw",
        kafka_topics_clean="test.clean",
        kafka_topics_dlq="test.dlq",
        kafka_topic_partitions=1,
        kafka_topic_replication_factor=1,
    )
    first = ensure_topics(settings)
    assert sorted(first) == ["test.clean", "test.dlq", "test.raw"]
    assert ensure_topics(settings) == []  # second run: nothing to do, no error

    meta = AdminClient({"bootstrap.servers": kafka}).list_topics(timeout=10)
    for name in ("test.raw", "test.clean", "test.dlq"):
        assert len(meta.topics[name].partitions) == 1
