"""One-time cleanup of the files the old theme digest left behind (design C-78).

The old version wrote `baseline.json`, a `latest.md` and dated `YYYY-MM-DD/HHMM.md`
digests with no marker on their first line. The story-first digest starts every file
with `MARKER`, so "old" means: `baseline.json`, or a digest file without the marker.

This deletes files, so it is careful: it only looks at `baseline.json`, `latest.md`
and `YYYY-MM-DD/HHMM.md` directly under the output folder; it never follows a symlink;
it keeps anything it cannot prove old (unknown names, unreadable files); it removes
only the date folders its own deletion emptied; and it lists what it will delete
before it deletes. Only the command `clean-old` runs it, never the hourly loop.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from whathappen.domain.render import MARKER

LEGACY_STATE_FILE = "baseline.json"
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGEST_FILE = re.compile(r"^\d{4}\.md$")


@dataclass(frozen=True)
class Scan:
    old: tuple[Path, ...]  # provably written by the old version
    kept: tuple[Path, ...]  # unknown, unreadable or a symlink: left alone


def _first_line_is_marker(path: Path) -> bool | None:
    """True if the file starts with the marker; None if it cannot be read as text."""
    try:
        with path.open(encoding="utf-8") as handle:
            return handle.readline().strip() == MARKER
    except (OSError, UnicodeDecodeError):
        return None


def scan(output_dir: Path) -> Scan:
    """Sort the known files under `output_dir` into old and kept (new files are
    neither: they are not listed at all)."""
    old: list[Path] = []
    kept: list[Path] = []

    def classify_digest(path: Path) -> None:
        marked = _first_line_is_marker(path)
        if marked is None:
            kept.append(path)
        elif not marked:
            old.append(path)

    for entry in sorted(output_dir.iterdir()):
        if entry.is_symlink():
            kept.append(entry)
        elif entry.is_file():
            if entry.name == LEGACY_STATE_FILE:
                old.append(entry)
            elif entry.name == "latest.md":
                classify_digest(entry)
            else:
                kept.append(entry)
        elif entry.is_dir() and _DATE_DIR.match(entry.name):
            for child in sorted(entry.iterdir()):
                if child.is_symlink():
                    kept.append(child)
                elif child.is_file() and _DIGEST_FILE.match(child.name):
                    classify_digest(child)
                else:
                    kept.append(child)
        else:
            kept.append(entry)  # another folder: listed, never entered
    return Scan(tuple(old), tuple(kept))


def remove(paths: Sequence[Path], output_dir: Path) -> tuple[int, int]:
    """Delete the files, then the date folders they emptied; returns the counts.

    Each path is checked again to be a plain file inside `output_dir`."""
    root = output_dir.resolve()
    files = folders = 0
    parents: set[Path] = set()
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        path.unlink()
        files += 1
        if path.parent != output_dir:
            parents.add(path.parent)
    for parent in sorted(parents):
        if _DATE_DIR.match(parent.name) and not any(parent.iterdir()):
            parent.rmdir()
            folders += 1
    return files, folders


def _show(root: Path, paths: Sequence[Path]) -> str:
    return "\n".join(f"  {p.relative_to(root).as_posix()}" for p in paths)


def run(output_dir: Path, *, dry_run: bool, out: TextIO) -> int:
    """List the old files and, unless `dry_run`, delete them. Returns an exit code."""
    if not output_dir.is_dir():
        print(f"Nothing to clean: {output_dir} does not exist.", file=out)
        return 0
    found = scan(output_dir)
    if found.kept:
        print(f"Kept, not touched ({len(found.kept)}):", file=out)
        print(_show(output_dir, found.kept), file=out)
    if not found.old:
        print(f"No old output found in {output_dir}.", file=out)
        return 0
    print(f"Old output in {output_dir} ({len(found.old)} files):", file=out)
    print(_show(output_dir, found.old), file=out)
    if dry_run:
        print(
            "Dry run: nothing was deleted. Run `make clean-old-yes` to delete these.",
            file=out,
        )
        return 0
    try:
        files, folders = remove(found.old, output_dir)
    except OSError as exc:
        print(f"Could not delete everything: {exc}", file=out)
        return 1
    folder_word = "folder" if folders == 1 else "folders"
    print(f"Deleted {files} files and {folders} empty date {folder_word}.", file=out)
    return 0
