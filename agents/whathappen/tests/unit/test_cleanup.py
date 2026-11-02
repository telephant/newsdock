"""TC-17, TC-18 (AC-14): the one-time cleanup of the old theme digest's output."""

import io
from pathlib import Path

import pytest

from whathappen import cli
from whathappen.adapters import cleanup
from whathappen.domain.render import MARKER

OLD_DIGEST = "# What happened · 2026-10-30 14:07 UTC (1840 articles · since 13:07)\n"
NEW_DIGEST = f"{MARKER}\n# What happened · 2026-11-02 09:05 UTC (1613 new articles)\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def out(tmp_path: Path) -> Path:
    """An output folder as the old version left it, plus two new-format files."""
    root = tmp_path / "output"
    write(root / "2026-10-30" / "1407.md", OLD_DIGEST)
    write(root / "2026-10-30" / "1507.md", OLD_DIGEST + "more\n")
    write(root / "2026-10-31" / "0905.md", NEW_DIGEST)
    write(root / "2026-11-02" / "0905.md", NEW_DIGEST)
    write(root / "latest.md", OLD_DIGEST)
    write(root / "baseline.json", '{"version": 1, "entries": []}')
    return root


def relative(root: Path, paths: tuple[Path, ...]) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in paths)


def tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


OLD = ["2026-10-30/1407.md", "2026-10-30/1507.md", "baseline.json", "latest.md"]


# --- TC-17: what is old, a dry run, the real run ------------------------------------
def test_the_scan_finds_exactly_the_old_files(out: Path) -> None:
    found = cleanup.scan(out)
    assert relative(out, found.old) == OLD
    assert found.kept == ()


def test_a_dry_run_lists_the_old_files_and_deletes_nothing(out: Path) -> None:
    before = tree(out)
    buffer = io.StringIO()
    assert cleanup.run(out, dry_run=True, out=buffer) == 0
    assert tree(out) == before
    report = buffer.getvalue()
    for name in OLD:
        assert name in report
    assert "2026-10-31/0905.md" not in report and "2026-11-02/0905.md" not in report
    assert "Dry run" in report and "nothing was deleted" in report


def test_the_real_run_deletes_exactly_those_and_the_emptied_folders(out: Path) -> None:
    new_before = {k: v for k, v in tree(out).items() if k not in OLD}
    buffer = io.StringIO()
    assert cleanup.run(out, dry_run=False, out=buffer) == 0
    after = tree(out)
    assert after == new_before  # the new files are byte-identical, nothing else is gone
    assert not (out / "2026-10-30").exists()  # emptied by the deletion
    assert (out / "2026-10-31").is_dir() and (out / "2026-11-02").is_dir()
    assert "Deleted 4 files and 1 empty date folder" in buffer.getvalue()


def test_a_second_run_finds_nothing(out: Path) -> None:
    cleanup.run(out, dry_run=False, out=io.StringIO())
    buffer = io.StringIO()
    assert cleanup.run(out, dry_run=False, out=buffer) == 0
    assert "No old output" in buffer.getvalue()


def test_a_new_format_latest_is_kept(out: Path) -> None:
    write(out / "latest.md", NEW_DIGEST)
    assert "latest.md" not in relative(out, cleanup.scan(out).old)
    cleanup.run(out, dry_run=False, out=io.StringIO())
    assert (out / "latest.md").read_text() == NEW_DIGEST


def test_only_the_first_line_decides(out: Path) -> None:
    # a marker further down does not make a file new; an old file may mention it
    write(out / "2026-10-29" / "0001.md", OLD_DIGEST + MARKER + "\n")
    assert "2026-10-29/0001.md" in relative(out, cleanup.scan(out).old)


# --- TC-18: safety --------------------------------------------------------------------
def test_unknown_files_and_folders_are_kept_and_listed(out: Path) -> None:
    write(out / "notes.txt", "mine\n")
    write(out / "2026-10-30" / "readme.txt", "mine too\n")
    write(out / "archive" / "1407.md", OLD_DIGEST)  # not a date folder
    buffer = io.StringIO()
    cleanup.run(out, dry_run=False, out=buffer)
    assert (out / "notes.txt").read_text() == "mine\n"
    assert (out / "2026-10-30" / "readme.txt").exists()
    assert (out / "archive" / "1407.md").read_text() == OLD_DIGEST
    # the date folder still holds an unknown file, so it is not removed
    assert (out / "2026-10-30").is_dir()
    report = buffer.getvalue()
    for kept in ("notes.txt", "readme.txt", "archive"):
        assert kept in report
    assert "kept" in report.lower()


def test_symlinks_are_neither_followed_nor_touched(tmp_path: Path, out: Path) -> None:
    outside = tmp_path / "outside"
    precious = write(outside / "precious.md", OLD_DIGEST)  # old-looking, not ours
    write(outside / "2026-01-01" / "0000.md", OLD_DIGEST)
    (out / "latest.md").unlink()
    (out / "latest.md").symlink_to(precious)
    (out / "2026-01-01").symlink_to(outside / "2026-01-01", target_is_directory=True)
    (out / "2026-10-30" / "0900.md").symlink_to(precious)
    cleanup.run(out, dry_run=False, out=io.StringIO())
    assert precious.read_text() == OLD_DIGEST
    assert (outside / "2026-01-01" / "0000.md").read_text() == OLD_DIGEST
    assert (out / "latest.md").is_symlink()
    assert (out / "2026-01-01").is_symlink()
    assert (out / "2026-10-30" / "0900.md").is_symlink()


def test_an_unreadable_file_is_kept_not_deleted(out: Path) -> None:
    (out / "2026-10-29").mkdir()
    (out / "2026-10-29" / "0001.md").write_bytes(b"\xff\xfe not utf-8 \x00")
    cleanup.run(out, dry_run=False, out=io.StringIO())
    assert (out / "2026-10-29" / "0001.md").exists()


def test_a_missing_or_empty_folder_is_a_clean_no_op(tmp_path: Path) -> None:
    buffer = io.StringIO()
    assert cleanup.run(tmp_path / "nowhere", dry_run=False, out=buffer) == 0
    assert "Nothing to clean" in buffer.getvalue()
    empty = tmp_path / "empty"
    empty.mkdir()
    buffer = io.StringIO()
    assert cleanup.run(empty, dry_run=False, out=buffer) == 0
    assert "No old output" in buffer.getvalue()


def test_a_failing_delete_is_reported_and_exits_nonzero(
    out: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "unlink", refuse)
    buffer = io.StringIO()
    assert cleanup.run(out, dry_run=False, out=buffer) == 1
    assert "read-only" in buffer.getvalue()


# --- the command line and the loop -------------------------------------------------
def test_the_command_runs_the_cleanup_and_builds_no_cycle(
    out: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("WHATHAPPEN_OUTPUT_DIR", str(out))

    def no_cycle(settings: object) -> None:
        raise AssertionError("the cleanup must not build the digest cycle")

    monkeypatch.setattr(cli, "build_cycle", no_cycle)
    before = tree(out)
    assert cli.main(["clean-old", "--dry-run"]) == 0
    assert tree(out) == before
    assert "baseline.json" in capsys.readouterr().out
    assert cli.main(["clean-old"]) == 0
    assert (
        not (out / "baseline.json").exists()
        and (out / "2026-11-02" / "0905.md").exists()
    )


def test_the_loop_and_once_never_call_the_cleanup(
    out: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHATHAPPEN_OUTPUT_DIR", str(out))
    monkeypatch.setenv("WHATHAPPEN_HEARTBEAT_FILE", str(out.parent / "healthy"))

    class Cycle:
        def run_once(self, now: object) -> None:
            return None

    def forbidden(*args: object, **kwargs: object) -> int:
        raise AssertionError("the loop must never run the cleanup")

    monkeypatch.setattr(cleanup, "run", forbidden)
    monkeypatch.setattr(cli, "build_cycle", lambda settings: Cycle())
    before = tree(out)
    assert cli.main(["--once"]) == 0
    assert tree(out) == before  # the old files are still there
