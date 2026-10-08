"""TC-27 + TC-33: agent network isolation and worker heartbeat healthchecks.

Brings up the full apps profile once (project `newsdock-e2e`); needs Docker,
ports 5433/29092/8000/3000 free. The ingester WILL poll the live GDELT feed
(one cycle; respects the 15-min rule by design).
"""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "newsdock-e2e"


def _compose(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "--profile", "apps", "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout,
    )  # fmt: skip


@pytest.fixture(scope="module")
def stack() -> Iterator[None]:
    up = _compose("up", "-d", "--wait", "--build", timeout=1800)
    if up.returncode != 0:
        _compose("down", "-v", "--remove-orphans")
        pytest.fail(f"stack did not come up healthy:\n{up.stderr[-3000:]}")
    yield
    _compose("down", "-v", "--remove-orphans")


def _exec(service: str, *cmd: str) -> subprocess.CompletedProcess[str]:
    return _compose("exec", "-T", service, *cmd)


# TC-27: no DB/Kafka env vars and no route from the agent container
def test_agent_has_no_db_or_kafka_env(stack: None) -> None:
    result = _exec("agent", "env")
    assert result.returncode == 0, result.stderr
    env_text = result.stdout
    assert "DATABASE_URL" not in env_text
    assert "KAFKA" not in env_text
    assert "POSTGRES" not in env_text
    assert "MCP_URL" in env_text and "OLLAMA_URL" in env_text


PROBE = (
    "import socket,sys\n"
    "try:\n"
    "    socket.create_connection(('{host}', {port}), timeout=3)\n"
    "except OSError:\n"
    "    sys.exit(1)\n"
    "sys.exit(0)\n"
)


@pytest.mark.parametrize("host,port", [("postgres", 5432), ("kafka", 9092)])
def test_agent_cannot_reach_data_services(stack: None, host: str, port: int) -> None:
    probe = _exec("agent", "python", "-c", PROBE.format(host=host, port=port))
    assert probe.returncode != 0, f"agent reached {host}:{port}"


def test_agent_reaches_the_api(stack: None) -> None:
    probe = _exec("agent", "python", "-c", PROBE.format(host="api", port=8000))
    assert probe.returncode == 0, "agent cannot reach the api service"


# TC-33 / externalize-config TC-22: the app healthcheck passes on a fresh heartbeat
# (max age written by the worker itself) and fails on a stale one
@pytest.mark.parametrize("service", ["ingester", "processor", "sink", "agent"])
def test_heartbeat_check_fresh_vs_stale(stack: None, service: str) -> None:
    check = f"python -m newsdock_{service}.adapters.healthcheck"
    fresh = _exec(service, "sh", "-c", check)
    assert fresh.returncode == 0, f"{service}: heartbeat missing or stale"
    stale = _exec(
        service, "sh", "-c", f"touch -d '2 hours ago' /tmp/healthy && {check}"
    )
    assert stale.returncode != 0, f"{service}: stale heartbeat passed the check"
    _exec(service, "sh", "-c", "touch /tmp/healthy")  # restore


def test_all_eight_services_report_healthy(stack: None) -> None:
    result = _compose("ps", "--format", "json")
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    states = {
        row["Service"]: (row.get("Health") or row.get("State"))
        for row in rows
        if row.get("Service") not in ("topics", "migrate")  # run-to-completion
    }
    assert set(states) == {
        "kafka", "postgres", "ingester", "processor", "sink", "api", "agent", "web",
    }  # fmt: skip
    unhealthy = {s: h for s, h in states.items() if h != "healthy"}
    assert not unhealthy, f"not healthy: {unhealthy}"
