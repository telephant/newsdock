"""TC-19…TC-22: `make up` / `make down` for Kafka and Postgres (AC-9).

Runs in its own compose project (`newsdock-test`) so a real dev stack is untouched.
Needs the ports 5433 and 29092 free.
"""

import json
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "newsdock-test"


def run(*cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd), cwd=ROOT, capture_output=True, text=True, check=False
    )


def compose(*args: str) -> subprocess.CompletedProcess[str]:
    return run("docker", "compose", "-p", PROJECT, "-f", "infra/compose.yaml", *args)


def make(target: str) -> subprocess.CompletedProcess[str]:
    return run("make", target, f"COMPOSE_PROJECT_NAME={PROJECT}")


def services() -> dict[str, dict[str, object]]:
    out = compose("--env-file", ".env.example", "ps", "--all", "--format", "json")
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
    return {str(row["Service"]): row for row in rows}


def psql(sql: str) -> str:
    result = compose(
        "--env-file", ".env.example", "exec", "-T", "postgres",
        "sh", "-c", f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "{sql}"',
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def env_file() -> Iterator[Path]:
    """A `.env` copied from `.env.example`; restores the owner's own `.env`."""
    target = ROOT / ".env"
    backup = ROOT / ".env.pre-test"
    if target.exists():
        target.rename(backup)
    shutil.copy(ROOT / ".env.example", target)
    try:
        yield target
    finally:
        compose("--env-file", ".env.example", "down", "-v", "--remove-orphans")
        target.unlink(missing_ok=True)
        if backup.exists():
            backup.rename(target)


@pytest.fixture
def no_env_file() -> Iterator[None]:
    target = ROOT / ".env"
    backup = ROOT / ".env.pre-test"
    if target.exists():
        target.rename(backup)
    try:
        yield
    finally:
        if backup.exists():
            backup.rename(target)


def test_up_without_env_file_fails_with_instruction(no_env_file: None) -> None:  # TC-20
    result = make("up")
    assert result.returncode != 0
    assert "copy .env.example to .env" in result.stdout + result.stderr


def test_up_makes_kafka_and_postgres_healthy(env_file: Path) -> None:  # TC-19
    result = make("up")
    assert result.returncode == 0, result.stdout + result.stderr
    found = services()
    for name in ("kafka", "postgres"):
        assert found[name]["Health"] == "healthy", found[name]
    available = psql("select count(*) from pg_available_extensions where name='vector'")
    assert available == "1"


def test_published_ports_are_bound_to_localhost(env_file: Path) -> None:  # TC-21
    assert make("up").returncode == 0
    published = [
        pub
        for row in services().values()
        for pub in row.get("Publishers") or []  # type: ignore[attr-defined]
        if pub["PublishedPort"]
    ]
    assert published, "expected published ports"
    assert {pub["URL"] for pub in published} == {"127.0.0.1"}


def test_down_then_up_recovers_and_keeps_data(env_file: Path) -> None:  # TC-22
    assert make("up").returncode == 0
    psql("create table survive (id int); insert into survive values (7)")
    assert make("down").returncode == 0
    time.sleep(1)
    assert services().get("postgres", {}).get("State") != "running"
    assert make("up").returncode == 0
    assert psql("select id from survive") == "7"


TOPICS = ["gkg.raw", "gkg.clean", "gkg.dlq"]


def describe_topics() -> list[str]:
    result = compose(
        "--env-file", ".env.example", "exec", "-T", "kafka",
        "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "kafka:9092",
        "--describe",
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    return sorted(
        " ".join(line.split()).split(" TopicId:")[0]
        + " "
        + " ".join(line.split()).split("PartitionCount:")[1]
        for line in result.stdout.splitlines()
        if line.startswith("Topic:")
    )


def test_up_creates_the_three_single_partition_topics(env_file: Path) -> None:  # TC-23
    assert make("up").returncode == 0
    described = describe_topics()
    assert len(described) == 3
    for topic in TOPICS:
        row = next(d for d in described if d.startswith(f"Topic: {topic} "))
        assert "1 ReplicationFactor: 1" in row, row


def test_topic_setup_is_idempotent(env_file: Path) -> None:  # TC-24
    assert make("up").returncode == 0
    before = describe_topics()
    second = make("topics")
    assert second.returncode == 0, second.stdout + second.stderr
    assert describe_topics() == before


def test_topics_job_waits_for_a_restarting_kafka(env_file: Path) -> None:  # TC-25
    assert make("up").returncode == 0
    assert compose("--env-file", ".env.example", "restart", "kafka").returncode == 0
    result = make("topics")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(describe_topics()) == 3


def test_migrate_twice_keeps_one_revision_and_the_extension(
    env_file: Path,
) -> None:  # TC-26
    assert make("up").returncode == 0  # includes the first migrate run
    second = make("migrate")
    assert second.returncode == 0, second.stdout + second.stderr
    assert psql("select version_num from alembic_version") == "0001"
    assert psql("select extname from pg_extension where extname='vector'") == "vector"


def test_migrate_fails_when_postgres_is_stopped(env_file: Path) -> None:  # TC-27
    assert make("up").returncode == 0
    assert compose("--env-file", ".env.example", "stop", "postgres").returncode == 0
    assert make("migrate").returncode != 0
