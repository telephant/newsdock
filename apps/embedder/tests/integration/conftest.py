"""A throwaway Postgres on a side port, so Docker tests run beside a dev stack.

Same fixture as the API and sink integration tests (apps may not import each
other's tests, so each keeps a copy).
"""

import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SIDE_PORT = "55435"


@pytest.fixture(scope="module")
def side_db(request: pytest.FixtureRequest) -> Iterator[tuple[str, str]]:
    """Yields (SQLAlchemy URL, libpq DSN) of the side Postgres."""
    project = "newsdock-embside-" + request.module.__name__.rsplit(".", 1)[-1].replace(
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
