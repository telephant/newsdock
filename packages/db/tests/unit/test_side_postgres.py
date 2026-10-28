"""`side_postgres` must not trust `docker compose up --wait`'s exit code.

Compose returns 0 even when the container could not bind its host port. A test that
trusted it talked to whatever listened on that port (once, the dev database), so the
helper also checks the container state, its health and the published port.
"""

import json
import subprocess
from collections.abc import Callable

import pytest
from newsdock_db.testing import _service_is_up, side_postgres


def ps_row(state: str = "running", health: str = "healthy") -> str:
    return json.dumps({"Service": "postgres", "State": state, "Health": health}) + "\n"


class FakeCompose:
    """Stands in for subprocess.run; records each compose subcommand."""

    def __init__(
        self,
        *,
        up_rc: int = 0,
        ps_out: str | None = None,
        port_out: Callable[[int], str] = lambda p: f"127.0.0.1:{p}\n",
    ) -> None:
        self.up_rc = up_rc
        self.ps_out = ps_row() if ps_out is None else ps_out
        self.port_out = port_out
        self.commands: list[str] = []
        self.projects: set[str] = set()
        self.env_ports: list[int] = []

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.projects.add(argv[argv.index("-p") + 1])
        env_file = argv[argv.index("--env-file") + 1]
        with open(env_file) as f:
            for line in f.read().splitlines():
                if line.startswith("POSTGRES_PORT="):
                    self.env_ports.append(int(line.split("=")[1]))
        sub = argv[argv.index("infra/compose.yaml") + 1]
        self.commands.append(sub)
        out, rc = "", 0
        if sub == "up":
            rc = self.up_rc
        elif sub == "ps":
            out = self.ps_out
        elif sub == "port":
            out = self.port_out(self.env_ports[-1])
        return subprocess.CompletedProcess(argv, rc, out, "")


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeCompose) -> None:
    monkeypatch.setattr("newsdock_db.testing.subprocess.run", fake)


def test_the_dev_project_is_refused() -> None:
    with pytest.raises(ValueError, match="dev compose project"):
        with side_postgres("newsdock"):
            pass


def test_service_is_up_needs_running_and_healthy() -> None:
    assert _service_is_up(ps_row(), "postgres")
    assert not _service_is_up(ps_row(state="exited"), "postgres")
    assert not _service_is_up(ps_row(state="created", health=""), "postgres")
    assert not _service_is_up(ps_row(health="starting"), "postgres")
    assert not _service_is_up("", "postgres")
    assert not _service_is_up(ps_row(), "kafka")


def test_success_yields_urls_on_a_free_port_and_always_tears_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeCompose()
    install(monkeypatch, fake)
    with side_postgres("newsdock-unit-test") as (url, dsn):
        port = fake.env_ports[0]
        assert port not in (5433, 5432) and port > 1024
        assert f"127.0.0.1:{port}/" in url and f"port={port} " in dsn
    assert fake.commands[0] == "up" and fake.commands[-1] == "down"
    assert fake.projects == {"newsdock-unit-test"}


def test_exit_code_zero_is_not_enough_when_the_container_is_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeCompose(up_rc=0, ps_out=ps_row(state="created", health=""))
    install(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="did not start"):
        with side_postgres("newsdock-unit-test"):
            pytest.fail("the body must not run")
    assert fake.commands[-1] == "down"


def test_a_port_that_is_not_ours_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCompose(port_out=lambda p: "127.0.0.1:5433\n")  # the dev database
    install(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="did not start"):
        with side_postgres("newsdock-unit-test"):
            pytest.fail("the body must not run")
    assert fake.commands[-1] == "down"


def test_a_failing_compose_up_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCompose(up_rc=1)
    install(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="did not start"):
        with side_postgres("newsdock-unit-test"):
            pytest.fail("the body must not run")


def test_each_start_picks_its_own_port(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCompose()
    install(monkeypatch, fake)
    with side_postgres("newsdock-unit-test"):
        pass
    with side_postgres("newsdock-unit-test"):
        pass
    assert len(fake.env_ports) >= 2  # read fresh from each start's env file
