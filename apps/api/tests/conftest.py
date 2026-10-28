"""A throwaway Postgres on a side port, so Docker tests run beside a dev stack.

The older Docker tests use the port in `.env.example` (5433), which a running
`make up` holds. Tests that take `side_db` start their own compose project on
`SIDE_PORT` from a temporary copy of `.env.example` and never touch the dev stack
or its volume. They need Docker but not a free 5433.
"""

import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SIDE_PORT = "55433"


@pytest.fixture(scope="module")
def side_db(request: pytest.FixtureRequest) -> Iterator[tuple[str, str]]:
    """Yields (SQLAlchemy URL, libpq DSN) of the side Postgres."""
    project = "newsdock-side-" + request.module.__name__.rsplit(".", 1)[-1].replace(
        "_", "-"
    )
    env_dir = Path(tempfile.mkdtemp())
    env_file = env_dir / "env"
    lines = (ROOT / ".env.example").read_text().splitlines()
    env_file.write_text(
        "\n".join(
            f"POSTGRES_PORT={SIDE_PORT}" if x.startswith("POSTGRES_PORT=") else x
            for x in lines
        )
    )
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in lines
            if "=" in line and not line.startswith("#")
        )
    }

    def compose(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", "-p", project, "--env-file", str(env_file),
             "-f", "infra/compose.yaml", *args],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )  # fmt: skip

    up = compose("up", "-d", "--wait", "postgres")
    assert up.returncode == 0, up.stderr
    mp = pytest.MonkeyPatch()
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{SIDE_PORT}/{env['POSTGRES_DB']}"
    )
    dsn = (
        f"host=127.0.0.1 port={SIDE_PORT} user={env['POSTGRES_USER']} "
        f"password={env['POSTGRES_PASSWORD']} dbname={env['POSTGRES_DB']}"
    )
    mp.setenv("DATABASE_URL", url)
    try:
        yield url, dsn
    finally:
        mp.undo()
        compose("down", "-v", "--remove-orphans")
