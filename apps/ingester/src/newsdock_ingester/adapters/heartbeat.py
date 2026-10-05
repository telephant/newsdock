"""Heartbeat file for the compose healthcheck (design-detail §4, R-4)."""

from pathlib import Path


class Heartbeat:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def touch(self) -> None:
        self._path.touch()
