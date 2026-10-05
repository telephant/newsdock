"""TC-9: a bad row through the running processor lands on gkg.dlq (Docker)."""

import json
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from confluent_kafka import Consumer, Producer
from newsdock_core.contracts import RawMessage
from newsdock_processor.adapters.kafka import KafkaProcessorLoop
from newsdock_processor.config import Settings

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
PROJECT = "newsdock-proc-test"
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
    assert _compose("up", "-d", "--wait", "kafka").returncode == 0
    assert _compose("run", "--rm", "topics").returncode == 0
    yield BOOTSTRAP
    _compose("down", "-v", "--remove-orphans")


def _consume(topic: str, n: int) -> list[tuple[str, dict[str, object]]]:
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": f"tc9-{uuid.uuid4()}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })  # fmt: skip
    consumer.subscribe([topic])
    out: list[tuple[str, dict[str, object]]] = []
    while len(out) < n:
        msg = consumer.poll(10.0)
        assert msg is not None, f"only {len(out)}/{n} messages on {topic}"
        assert msg.error() is None
        key, value = msg.key(), msg.value()
        assert key is not None and value is not None
        out.append((key.decode(), json.loads(value)))
    consumer.close()
    return out


def test_processor_routes_good_and_bad_rows(kafka: str) -> None:
    good = (FIXTURES / "gkg_sample.tsv").read_text().splitlines()[0]
    with (FIXTURES / "bad_rows.json").open() as f:
        bad = next(b for b in json.load(f) if b["name"] == "no_title_tag")

    producer = Producer({"bootstrap.servers": kafka})
    for row_no, line in enumerate([good, bad["line"]]):
        raw = RawMessage(slot=SLOT, row_no=row_no, line=line)
        producer.produce("gkg.raw", key=f"{SLOT}:{row_no}".encode(),
                         value=raw.model_dump_json().encode())  # fmt: skip
    producer.flush()

    settings = Settings(kafka_bootstrap_servers=kafka)
    loop = KafkaProcessorLoop(settings, group_id=f"proc-{uuid.uuid4()}")
    processed = loop.run_once(max_messages=2, timeout_seconds=20.0)
    loop.close()
    assert processed == 2

    (clean_key, clean) = _consume("gkg.clean", 1)[0]
    assert clean_key == clean["url_hash"] and clean["slot"] == SLOT
    (dlq_key, dlq) = _consume("gkg.dlq", 1)[0]
    assert dlq_key == f"{SLOT}:1"
    assert dlq["reason"] == "missing_title"
    line = dlq["line"]
    assert isinstance(line, str) and len(line) <= 2048
