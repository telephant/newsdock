"""Per-account login failure limiter (spec AC-13, design C-10).

A window opens at the first failure of an account; once `max_failures` land inside
it, `check` refuses until the window ends. A success clears the account. In memory,
valid for one API worker (same assumption as the agent limiter). The key is the
normalized email, so unknown emails cost memory too: old windows are pruned and the
table has a hard cap. `max_failures == 0` disables limiting.
"""

import math
import time
from collections.abc import Callable

from newsdock_api.domain.ratelimit import Decision


class LoginLimiter:
    def __init__(
        self,
        max_failures: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_entries: int = 10_000,
        prune_above: int = 1_000,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._prune_above = prune_above
        # key -> (failures, window start)
        self._entries: dict[str, tuple[int, float]] = {}

    @staticmethod
    def _key(raw: str) -> str:
        return raw.strip().lower()

    def check(self, raw_key: str) -> Decision:
        if self._max <= 0:
            return Decision(True)
        entry = self._entries.get(self._key(raw_key))
        if entry is None:
            return Decision(True)
        count, start = entry
        now = self._clock()
        if now - start >= self._window:
            return Decision(True)
        if count < self._max:
            return Decision(True)
        return Decision(False, max(1, math.ceil(start + self._window - now)))

    def record_failure(self, raw_key: str) -> None:
        if self._max <= 0:
            return
        key = self._key(raw_key)
        now = self._clock()
        entry = self._entries.pop(key, None)  # re-insert last: dict order = recency
        if entry is None or now - entry[1] >= self._window:
            self._entries[key] = (1, now)
        else:
            self._entries[key] = (entry[0] + 1, entry[1])  # window is not extended
        if len(self._entries) > self._prune_above:
            self._prune(now)

    def clear(self, raw_key: str) -> None:
        self._entries.pop(self._key(raw_key), None)

    def tracked(self) -> int:
        return len(self._entries)

    def _prune(self, now: float) -> None:
        self._entries = {
            k: v for k, v in self._entries.items() if now - v[1] < self._window
        }
        while len(self._entries) > self._max_entries:  # oldest first
            del self._entries[next(iter(self._entries))]
