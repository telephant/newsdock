"""TC-2: the real producer publishes one message per row to gkg.raw (Docker).

Own compose project; needs port 29092 free.
"""

import json
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from confluent_kafka import Consumer
from newsdock_core.contracts import RawMessage
from newsdock_ingester.adapters.kafka import KafkaRawPublisher

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "packages" / "core" / "tests" / "fixtures" / "gkg_sample.tsv"
PROJECT = "newsdock-ing-test"
BOOTSTRAP = "127.0.0.1:29092"
SLOT = "20261004081500"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def kafka() -> Iterator[str]:
    up = _compose("up", "-d", "--wait", "kafka")
    assert up.returncode == 0, up.stderr
    topics = _compose("run", "--rm", "topics")
    assert topics.returncode == 0, topics.stderr
    yield BOOTSTRAP
    _compose("down", "-v", "--remove-orphans")


def test_one_raw_message_per_row(kafka: str) -> None:
    lines = FIXTURE.read_text().splitlines()
    publisher = KafkaRawPublisher(bootstrap_servers=kafka)
    for row_no, line in enumerate(lines):
        publisher.publish(
            f"{SLOT}:{row_no}", RawMessage(slot=SLOT, row_no=row_no, line=line)
        )
    publisher.flush()

    consumer = Consumer({
        "bootstrap.servers": kafka,
        "group.id": f"tc2-{uuid.uuid4()}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })  # fmt: skip
    consumer.subscribe(["gkg.raw"])
    got: list[tuple[str, dict[str, object]]] = []
    while len(got) < len(lines):
        msg = consumer.poll(10.0)
        assert msg is not None, f"only {len(got)} of {len(lines)} messages arrived"
        assert msg.error() is None, msg.error()
        key, value = msg.key(), msg.value()
        assert key is not None and value is not None
        got.append((key.decode(), json.loads(value)))
    consumer.close()

    assert [k for k, _ in got] == [f"{SLOT}:{i}" for i in range(len(lines))]
    first = got[0][1]
    assert first["slot"] == SLOT and first["line"] == lines[0]
