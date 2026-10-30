"""Pure helpers of the worker: a bounded skip list and a capped backoff."""


class SkipList:
    """Counts failures per key; a key failing `max_failures` times is excluded.

    Kept in memory only (a restart retries a title once more) and bounded: past
    `max_entries` the oldest entries are dropped, so one bad day cannot grow it.
    """

    def __init__(self, *, max_failures: int, max_entries: int) -> None:
        self._max_failures = max_failures
        self._max_entries = max_entries
        self._counts: dict[str, int] = {}

    def fail(self, key: str) -> None:
        self._counts[key] = self._counts.pop(key, 0) + 1  # re-insert: newest last
        while len(self._counts) > self._max_entries:
            del self._counts[next(iter(self._counts))]

    def forget(self, key: str) -> None:
        self._counts.pop(key, None)

    def excluded(self) -> frozenset[str]:
        return frozenset(k for k, n in self._counts.items() if n >= self._max_failures)


class Backoff:
    """Doubling delay from `base` up to `cap`; `reset` after a success."""

    def __init__(self, *, base: float, cap: float) -> None:
        if base <= 0 or cap < base:
            raise ValueError("backoff needs 0 < base <= cap")
        self._base = base
        self._cap = cap
        self._current = base

    def next(self) -> float:
        delay = self._current
        self._current = min(self._current * 2, self._cap)
        return delay

    def reset(self) -> None:
        self._current = self._base
