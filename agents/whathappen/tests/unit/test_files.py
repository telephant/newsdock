"""The digest writer (AC-12): atomic, and named by the UTC clock."""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from whathappen.adapters.files import DigestWriter

NOW = datetime(2026, 10, 30, 14, 7, tzinfo=UTC)


def fail_replace_for(monkeypatch: pytest.MonkeyPatch, name: str) -> Callable[[], int]:
    """Make os.replace raise when the destination is `name`; returns a call counter."""
    real = os.replace
    calls = {"n": 0}

    def replace(src: Any, dst: Any) -> None:
        if Path(dst).name == name:
            calls["n"] += 1
            raise OSError("simulated failure between temp write and rename")
        real(src, dst)

    monkeypatch.setattr("whathappen.adapters.files.os.replace", replace)
    return lambda: calls["n"]


# ---- TC-18: the digest writer ----------------------------------------------------


def test_tc18_writes_the_dated_file_and_latest_with_identical_text(
    tmp_path: Path,
) -> None:
    root = tmp_path / "digests"  # does not exist yet
    path = DigestWriter(root).write(NOW, "# digest\n")
    assert path == root / "2026-10-30" / "1407.md"
    assert path.read_text() == "# digest\n"
    assert (root / "latest.md").read_text() == "# digest\n"


def test_tc18_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    DigestWriter(tmp_path).write(NOW, "x\n")
    names = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    assert names == ["1407.md", "latest.md"]


def test_tc18_file_name_uses_utc_whatever_the_clock_zone(tmp_path: Path) -> None:
    local = datetime(2026, 10, 30, 23, 7, tzinfo=timezone(timedelta(hours=9)))
    path = DigestWriter(tmp_path).write(local, "x\n")
    assert path == tmp_path / "2026-10-30" / "1407.md"  # 23:07 +09:00 is 14:07 UTC


def test_tc18_a_second_digest_updates_latest_and_keeps_the_first(
    tmp_path: Path,
) -> None:
    writer = DigestWriter(tmp_path)
    writer.write(NOW, "first\n")
    writer.write(NOW + timedelta(hours=1), "second\n")
    assert (tmp_path / "2026-10-30" / "1407.md").read_text() == "first\n"
    assert (tmp_path / "2026-10-30" / "1507.md").read_text() == "second\n"
    assert (tmp_path / "latest.md").read_text() == "second\n"


def test_tc18_a_failure_between_temp_write_and_rename_keeps_the_old_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = DigestWriter(tmp_path)
    writer.write(NOW, "old\n")
    calls = fail_replace_for(monkeypatch, "latest.md")
    with pytest.raises(OSError):
        writer.write(NOW + timedelta(hours=1), "new\n")
    assert calls() == 1
    assert (tmp_path / "latest.md").read_text() == "old\n"  # never half-written
    assert not [p for p in tmp_path.rglob("*") if p.name.endswith(".tmp")]


def test_tc18_an_unwritable_directory_raises_oserror(tmp_path: Path) -> None:
    blocked = tmp_path / "ro"
    blocked.mkdir()
    blocked.chmod(0o500)
    try:
        with pytest.raises(OSError):
            DigestWriter(blocked / "digests").write(NOW, "x\n")
    finally:
        blocked.chmod(0o700)
