"""Container healthchecks that need no config value (ADR-0015).

A worker writes its own allowed heartbeat age into the heartbeat file on every beat;
the check compares the file's age (mtime) with that number.
"""

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path


def write_heartbeat(path: str, max_age_seconds: int) -> None:
    """Record a beat: the file's content is the allowed age, its mtime is the beat."""
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


def check_http(url: str, *, timeout_seconds: float) -> int:
    """Exit code: 0 on HTTP 200, else 1."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
            return 0 if response.status == 200 else 1
    except (urllib.error.URLError, OSError):
        return 1
