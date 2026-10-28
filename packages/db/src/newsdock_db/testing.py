"""Test helpers: a throwaway Postgres, and rows with known embeddings.

Lives in the package (not in a test folder) because apps may not import each
other's tests and pytest's importlib mode does not share sibling modules.
"""

import json
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from newsdock_db.models import Article

REPO_ROOT = Path(__file__).resolve().parents[4]
DEV_PROJECT = "newsdock"  # the compose project name of the real dev stack

DIMENSION = 768
NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def make_vec(*components: float) -> list[float]:
    """The given leading components, zero-padded to the column's 768 dimensions."""
    return [*components, *([0.0] * (DIMENSION - len(components)))]


def article(
    key: str,
    title: str,
    *,
    vec: list[float] | None = None,
    model: str | None = "m1",
    domain: str = "example.com",
    themes: list[str] | None = None,
    published_at: datetime = NOW,
) -> Article:
    """A canonical article row; `model` is stored only when a vector is given."""
    return Article(
        url_hash=key, gkg_record_id="x", slot="20261028120000",
        url=f"https://{domain}/{key}", title=title, domain=domain,
        published_at=published_at, themes=themes or [], persons=[], orgs=[],
        story_key=f"s {key}",
        embedding=vec, embedding_model=model if vec is not None else None,
    )  # fmt: skip


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _env_example() -> tuple[list[str], dict[str, str]]:
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    env = {
        key.strip(): value.strip()
        for key, _, value in (
            line.partition("=") for line in lines if "=" in line and line[:1] != "#"
        )
    }
    return lines, env


def _service_is_up(rows: str, service: str) -> bool:
    """True when `compose ps --format json` shows the service running and healthy."""
    for line in rows.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("Service") == service:
            return bool(
                row.get("State") == "running" and row.get("Health") == "healthy"
            )
    return False


@contextmanager
def side_postgres(project: str) -> Iterator[tuple[str, str]]:
    """A throwaway pgvector Postgres in its own compose project on a free port.

    Yields (SQLAlchemy URL, libpq DSN). Never touches the dev stack: the project
    name must differ from the dev project, the port is picked free at start, and
    the container is checked to be running and healthy and to own that port.
    `docker compose up --wait` returns 0 even when the container could not bind
    its port, so its exit code alone proves nothing; without these checks a test
    would silently talk to whatever listens on the port (the dev database).
    """
    if project == DEV_PROJECT:
        raise ValueError("refusing to use the dev compose project for a test database")
    lines, env = _env_example()
    port = _free_port()
    env_file = Path(tempfile.mkdtemp()) / "env"
    env_file.write_text(
        "\n".join(
            f"POSTGRES_PORT={port}" if x.startswith("POSTGRES_PORT=") else x
            for x in lines
        )
    )

    def compose(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", "-p", project, "--env-file", str(env_file),
             "-f", "infra/compose.yaml", *args],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )  # fmt: skip

    try:
        up = compose("up", "-d", "--wait", "postgres")
        status = compose("ps", "--format", "json", "postgres")
        published = compose("port", "postgres", "5432")
        if not (
            up.returncode == 0
            and _service_is_up(status.stdout, "postgres")
            and published.stdout.strip().endswith(f":{port}")
        ):
            logs = compose("logs", "--tail", "20", "postgres")
            raise RuntimeError(
                f"side Postgres for project {project} did not start on port {port}: "
                f"{up.stderr.strip()} {logs.stdout.strip()}"
            )
        user, password, db = (
            env["POSTGRES_USER"],
            env["POSTGRES_PASSWORD"],
            env["POSTGRES_DB"],
        )
        yield (
            f"postgresql+psycopg://{user}:{password}@127.0.0.1:{port}/{db}",
            f"host=127.0.0.1 port={port} user={user} password={password} dbname={db}",
        )
    finally:
        compose("down", "-v", "--remove-orphans")
