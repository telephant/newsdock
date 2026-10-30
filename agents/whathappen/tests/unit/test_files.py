"""File adapters (TC-9, TC-18, TC-20; AC-5, AC-12, AC-14): atomic and forgiving."""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from whathappen.adapters.files import BaselineStore, DigestWriter
from whathappen.domain.baseline import Baseline, BaselineEntry

NOW = datetime(2026, 10, 30, 14, 7, tzinfo=UTC)


def entry(i: int, **themes: int) -> BaselineEntry:
    return BaselineEntry(at=NOW + timedelta(hours=i), articles=1000, themes=themes)


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


# ---- TC-9: the baseline store reads forgivingly ------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        None,  # missing file
        "",
        "not json at all",
        "[]",
        '{"version": 2, "entries": []}',
        '{"version": 1, "entries": [{"at": "yesterday"}]}',
        '{"version": 1, "entries": "nope"}',
    ],
)
def test_tc9_missing_or_bad_files_load_as_an_empty_baseline(
    tmp_path: Path, content: str | None
) -> None:
    path = tmp_path / "digest-baseline.json"
    if content is not None:
        path.write_text(content)
    assert BaselineStore(path).load() == Baseline()


def test_tc9_a_bad_file_is_logged_but_a_missing_one_is_not_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    BaselineStore(tmp_path / "missing.json").load()
    assert not [r for r in caplog.records if r.levelname == "WARNING"]
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    BaselineStore(bad).load()
    assert [r for r in caplog.records if r.levelname == "WARNING"]


# ---- TC-20: the baseline store saves atomically -----------------------------------


def test_tc20_save_then_load_round_trips_and_creates_the_directory(
    tmp_path: Path,
) -> None:
    store = BaselineStore(tmp_path / "state" / "digest-baseline.json")
    baseline = Baseline(entries=[entry(0, A=3), entry(1, B=4)])
    store.save(baseline)
    assert store.load() == baseline


def test_tc20_a_failed_save_keeps_the_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "digest-baseline.json"
    store = BaselineStore(path)
    old = Baseline(entries=[entry(0, A=1)])
    store.save(old)
    fail_replace_for(monkeypatch, "digest-baseline.json")
    with pytest.raises(OSError):
        store.save(Baseline(entries=[entry(0, A=1), entry(1, A=2)]))
    monkeypatch.undo()
    assert BaselineStore(path).load() == old
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
