"""Per-agent request limiter (spec AC-11, D-8): fixed one-minute windows.

In memory, which is valid because the API runs one worker. The clock is
injectable for tests. `limit == 0` disables limiting.
"""

import math
import time
from collections.abc import Callable
from typing import NamedTuple

ANONYMOUS_BUCKET = "anonymous"  # all anonymous traffic shares this key (D-8)
WINDOW_SECONDS = 60


class Decision(NamedTuple):
    allowed: bool
    retry_after: int = 0


class FixedWindowLimiter:
    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._clock = clock
        self._window = -1
        self._counts: dict[str, int] = {}

    def allow(self, key: str) -> Decision:
        if self._limit <= 0:
            return Decision(True)
        now = self._clock()
        window = int(now // WINDOW_SECONDS)
        if window != self._window:  # roll over: drop every old counter
            self._window = window
            self._counts = {}
        count = self._counts.get(key, 0)
        if count >= self._limit:
            window_end = (window + 1) * WINDOW_SECONDS
            return Decision(False, max(1, math.ceil(window_end - now)))
        self._counts[key] = count + 1
        return Decision(True)

    def tracked(self) -> int:
        return len(self._counts)
