"""pytest plugin: Docker tests that need fixed host ports refuse to run on a busy port.

Some Docker tests start a whole stack on the dev stack's own host ports (Postgres
5433, Kafka 29092, API 8000, web 3000). `docker compose up --wait` exits 0 even when
a container could not bind its port, so with the dev stack running such a test does
not fail: it talks to the dev stack and, in its setup, truncates its tables, creates
topics or removes images (this happened once to the dev database).

Tests that take the `side_db` fixture start their own Postgres on a free port and
are exempt. Every other test marked `docker` must find these ports free, otherwise
it fails in setup, before any fixture starts a container, with a message that says
why. Stop the dev stack (`make down`) to run them.
"""

import socket
from collections.abc import Iterable

import pytest

FIXED_PORTS: dict[int, str] = {
    5433: "Postgres",
    29092: "Kafka",
    8000: "API",
    3000: "web",
}
EXEMPT_FIXTURE = "side_db"


def ports_in_use(ports: Iterable[int]) -> list[int]:
    """The ports something is already listening on at 127.0.0.1."""
    busy = []
    for port in ports:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                busy.append(port)
    return busy


def refusal(busy: list[int]) -> str:
    named = ", ".join(f"{port} ({FIXED_PORTS.get(port, '?')})" for port in busy)
    return (
        f"refusing to run: port(s) {named} already in use, probably by the dev stack. "
        "This Docker test starts its own stack on those fixed ports; `docker compose "
        "up --wait` would exit 0 anyway and the test would then use the dev stack's "
        "data. Stop the dev stack first (`make down`), or use a test that takes the "
        "`side_db` fixture."
    )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("docker") is None:
        return
    if EXEMPT_FIXTURE in getattr(item, "fixturenames", ()):
        return
    busy = ports_in_use(FIXED_PORTS)
    if busy:
        pytest.fail(refusal(busy), pytrace=False)
