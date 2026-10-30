"""File adapters of the digest: the digest writer and the baseline store (C-56).

Both write through a temp file in the same directory and `os.replace`, so a reader
never sees a half-written file. File names come from the clock only, never from
article text. The baseline is a cache: any problem reading it means "cold start".
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from whathappen.domain.baseline import Baseline

logger = logging.getLogger(__name__)

BASELINE_VERSION = 1


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


class BaselineStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Baseline:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Baseline()  # first run
        except OSError as exc:
            logger.warning("baseline unreadable (%s): starting cold", exc)
            return Baseline()
        try:
            baseline = Baseline.model_validate_json(raw)
        except ValidationError as exc:
            logger.warning(
                "baseline file invalid (%d problem(s)): starting cold",
                exc.error_count(),
            )
            return Baseline()
        if baseline.version != BASELINE_VERSION:
            logger.warning(
                "baseline version %s is not %s: starting cold",
                baseline.version,
                BASELINE_VERSION,
            )
            return Baseline()
        return baseline

    def save(self, baseline: Baseline) -> None:
        _atomic_write(self._path, baseline.model_dump_json())
