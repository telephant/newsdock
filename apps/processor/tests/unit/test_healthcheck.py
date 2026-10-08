"""TC-20/TC-21: the processor healthcheck module reads the configured heartbeat file."""

import os
from pathlib import Path

import pytest
from newsdock_config.health import write_heartbeat
from newsdock_processor.adapters.healthcheck import main


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSDOCK_CONFIG_FILE", raising=False)


def test_fresh_heartbeat_is_healthy_and_stale_one_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beat = tmp_path / "healthy"
    monkeypatch.setenv("NEWSDOCK_HEARTBEAT_FILE", str(beat))
    assert main() == 1  # no file yet
    write_heartbeat(str(beat), 120)
    assert main() == 0
    os.utime(beat, (1.0, 1.0))  # a very old beat
    assert main() == 1
