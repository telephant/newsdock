"""File adapter of the digest: the atomic digest writer (C-56).

It writes through a temp file in the same directory and `os.replace`, so a reader
never sees a half-written file. File names come from the clock only, never from
article text.
"""

import os
from datetime import UTC, datetime
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class DigestWriter:
    """Writes `<root>/YYYY-MM-DD/HHMM.md` (UTC run time) and `<root>/latest.md`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, now: datetime, text: str) -> Path:
        utc = now.astimezone(UTC)
        path = self._root / f"{utc:%Y-%m-%d}" / f"{utc:%H%M}.md"
        _atomic_write(path, text)
        _atomic_write(self._root / "latest.md", text)
        return path
