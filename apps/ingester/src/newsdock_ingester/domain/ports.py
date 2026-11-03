"""Ports the ingester cycle needs; adapters implement them with real I/O."""

from typing import Protocol

from newsdock_core.contracts import RawMessage
from pydantic import BaseModel


class SlotState(BaseModel):
    """Mirror of the `ingest_slot` row (design.md §4)."""

    slot: str
    status: str  # pending | published | failed
    attempts: int = 0
    row_count: int | None = None


class FileState(BaseModel):
    """Mirror of the `ingest_file` row: fetch state of an Events or Mentions file."""

    slot: str
    kind: str  # events | mentions
    status: str  # pending | published | failed
    attempts: int = 0
    row_count: int | None = None


class GdeltSource(Protocol):
    def fetch_index(self) -> str | None: ...

    def fetch(self, url: str) -> bytes | None: ...


class RawPublisher(Protocol):
    def publish(self, key: str, message: RawMessage) -> None: ...

    def flush(self) -> None: ...


class SlotRepo(Protocol):
    def get(self, slot: str) -> SlotState | None: ...

    def pending(self, max_attempts: int) -> list[SlotState]: ...

    def save(self, state: SlotState) -> None: ...


class FileRepo(Protocol):
    def get(self, slot: str, kind: str) -> FileState | None: ...

    def pending(self, max_attempts: int) -> list[FileState]: ...

    def save(self, state: FileState) -> None: ...
