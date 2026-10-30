"""The guard that keeps fixed-port Docker tests away from a running dev stack."""

import socket
from collections.abc import Iterator
from contextlib import contextmanager

import dev_stack_guard
import pytest


@contextmanager
def listening() -> Iterator[int]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        yield int(sock.getsockname()[1])


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_a_listening_port_is_reported_and_a_free_one_is_not() -> None:
    free = free_port()
    with listening() as busy:
        assert dev_stack_guard.ports_in_use([busy, free]) == [busy]
    assert dev_stack_guard.ports_in_use([free]) == []


def test_the_message_names_the_port_the_service_and_the_way_out() -> None:
    message = dev_stack_guard.refusal([5433, 29092])
    assert "5433 (Postgres)" in message and "29092 (Kafka)" in message
    assert "make down" in message and "side_db" in message


pytest_plugins = ["pytester"]

TEST_FILE = """
import pytest

@pytest.fixture(scope="module")
def started():
    print("FIXTURE-STARTED")  # stands for `compose up`
    yield

@pytest.mark.docker
def test_uses_fixed_ports(started):
    pass

@pytest.fixture(scope="module")
def side_db():
    yield ("url", "dsn")

@pytest.mark.docker
def test_uses_a_side_database(side_db):
    pass

def test_without_the_docker_marker():
    pass
"""


def run_guarded(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, ports: dict[int, str]
) -> pytest.RunResult:
    monkeypatch.setattr(dev_stack_guard, "FIXED_PORTS", ports)
    pytester.makepyfile(TEST_FILE)
    return pytester.runpytest_inprocess(
        "-p", "dev_stack_guard", "-m", "docker or not docker", "-s", "-q"
    )


def test_a_docker_test_on_a_busy_port_fails_before_its_fixture_starts(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    with listening() as busy:
        result = run_guarded(pytester, monkeypatch, {busy: "Postgres"})
    result.assert_outcomes(passed=2, errors=1)  # side_db test and unmarked test pass
    output = result.stdout.str()
    assert "refusing to run" in output and "make down" in output
    assert "FIXTURE-STARTED" not in output  # compose up never ran


def test_the_same_test_runs_when_the_ports_are_free(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_guarded(pytester, monkeypatch, {free_port(): "Postgres"})
    result.assert_outcomes(passed=3)
    assert "FIXTURE-STARTED" in result.stdout.str()
