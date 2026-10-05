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


class GdeltSource(Protocol):
    def fetch_index(self) -> str | None: ...

    def fetch_gkg(self, url: str) -> bytes | None: ...


class RawPublisher(Protocol):
    def publish(self, key: str, message: RawMessage) -> None: ...

    def flush(self) -> None: ...


class SlotRepo(Protocol):
    def get(self, slot: str) -> SlotState | None: ...

    def pending(self, max_attempts: int) -> list[SlotState]: ...

    def save(self, state: SlotState) -> None: ...
