"""Heartbeat file and the container healthcheck."""

import os
from pathlib import Path

import pytest

from whathappen.adapters import healthcheck
from whathappen.adapters.heartbeat import check_heartbeat, write_heartbeat


def test_a_fresh_beat_is_healthy_and_the_age_limit_is_in_the_file(
    tmp_path: Path,
) -> None:
    beat = tmp_path / "healthy"
    write_heartbeat(str(beat), 7200)
    assert beat.read_text() == "7200"
    assert check_heartbeat(str(beat)) == 0


def test_a_missing_empty_or_garbled_file_is_unhealthy(tmp_path: Path) -> None:
    beat = tmp_path / "healthy"
    assert check_heartbeat(str(beat)) == 1
    beat.write_text("")
    assert check_heartbeat(str(beat)) == 1
    beat.write_text("soon")
    assert check_heartbeat(str(beat)) == 1


def test_a_beat_older_than_its_own_limit_is_unhealthy(tmp_path: Path) -> None:
    beat = tmp_path / "healthy"
    write_heartbeat(str(beat), 120)
    os.utime(beat, (1.0, 1.0))
    assert check_heartbeat(str(beat)) == 1
    assert check_heartbeat(str(beat), now=100.0) == 0  # young enough at that "now"


def test_the_healthcheck_module_reads_the_configured_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beat = tmp_path / "healthy"
    monkeypatch.setenv("WHATHAPPEN_HEARTBEAT_FILE", str(beat))
    assert healthcheck.main() == 1
    write_heartbeat(str(beat), 120)
    assert healthcheck.main() == 0
