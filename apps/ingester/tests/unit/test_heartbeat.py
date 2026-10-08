"""TC-21 (ingester): each beat writes the settings-derived max age into the file."""

from pathlib import Path

from newsdock_ingester.adapters.heartbeat import Heartbeat


def test_touch_writes_the_max_age(tmp_path: Path) -> None:
    beat = tmp_path / "healthy"
    Heartbeat(str(beat), max_age_seconds=2400).touch()
    assert beat.read_text().strip() == "2400"
