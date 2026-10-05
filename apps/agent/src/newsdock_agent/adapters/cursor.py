"""Cursor file on the named volume agent_state (R-2 decision 2026-10-04)."""

import json
from pathlib import Path


class FileCursorStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load(self) -> str | None:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return None
        cursor = data.get("cursor")
        return str(cursor) if cursor else None

    def save(self, cursor: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"cursor": cursor}))
