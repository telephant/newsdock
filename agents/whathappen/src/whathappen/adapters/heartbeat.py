"""Liveness file shared by the loop and the container healthcheck.

The loop writes its own allowed age into the file on every beat; the check compares
the file's age (mtime) with that number, so it needs no configuration.
"""

import time
from collections.abc import Callable
from pathlib import Path


def write_heartbeat(path: str, max_age_seconds: int) -> None:
    Path(path).write_text(str(max_age_seconds))


def check_heartbeat(path: str, *, now: Callable[[], float] | float = time.time) -> int:
    """Exit code: 0 healthy, 1 missing / unreadable / too old."""
    current = now() if callable(now) else now
    try:
        target = Path(path)
        max_age = int(target.read_text().strip())
        age = current - target.stat().st_mtime
    except (OSError, ValueError):
        return 1
    return 0 if age <= max_age else 1
