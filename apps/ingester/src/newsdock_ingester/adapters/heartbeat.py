"""Heartbeat file for the compose healthcheck (design-detail §4, R-4, ADR-0015)."""

from newsdock_config.health import write_heartbeat


class Heartbeat:
    def __init__(self, path: str, *, max_age_seconds: int) -> None:
        self._path = path
        self._max_age_seconds = max_age_seconds

    def touch(self) -> None:
        write_heartbeat(self._path, self._max_age_seconds)
