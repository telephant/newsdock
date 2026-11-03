"""The entry point's wiring runs against a real database (needs Docker).

Throwaway Postgres from `side_db`; the queue is empty, so no site is contacted. It
proves the pieces fit together: settings, repo, fetcher, scheduler, worker, run loop and
the heartbeat file the container healthcheck reads.
"""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_extractor.__main__ import serve
from newsdock_extractor.adapters.healthcheck import main as healthcheck
from newsdock_extractor.config import Settings

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


def test_the_worker_runs_passes_and_keeps_its_heartbeat(
    side_db: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    beat = tmp_path / "healthy"
    monkeypatch.delenv("NEWSDOCK_CONFIG_FILE", raising=False)
    monkeypatch.setenv("NEWSDOCK_HEARTBEAT_FILE", str(beat))
    settings = Settings(poll_interval_seconds=0.01)
    assert healthcheck() == 1  # no heartbeat before the worker has run

    checks = {"n": 0}

    def stop_after_three_passes() -> bool:
        checks["n"] += 1
        return checks["n"] > 3

    asyncio.run(serve(settings, should_stop=stop_after_three_passes))
    assert checks["n"] == 4
    assert beat.exists()
    assert healthcheck() == 0  # fresh heartbeat: the container would be healthy
