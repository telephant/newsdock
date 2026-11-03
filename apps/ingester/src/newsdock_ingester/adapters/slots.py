"""ingest_slot repository over newsdock_db (role: ingester_rw)."""

from newsdock_db.models import IngestFile, IngestSlot
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from newsdock_ingester.domain.ports import FileState, SlotState


class SqlSlotRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, slot: str) -> SlotState | None:
        with Session(self._engine) as session:
            row = session.get(IngestSlot, slot)
            if row is None:
                return None
            return SlotState(
                slot=row.slot,
                status=row.status,
                attempts=row.attempts,
                row_count=row.row_count,
            )

    def pending(self, max_attempts: int) -> list[SlotState]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(IngestSlot)
                .where(IngestSlot.status == "pending")
                .where(IngestSlot.attempts < max_attempts)
                .order_by(IngestSlot.slot)
            ).all()
            return [
                SlotState(
                    slot=r.slot,
                    status=r.status,
                    attempts=r.attempts,
                    row_count=r.row_count,
                )
                for r in rows
            ]

    def save(self, state: SlotState) -> None:
        with Session(self._engine) as session:
            row = session.get(IngestSlot, state.slot)
            if row is None:
                row = IngestSlot(slot=state.slot, status=state.status)
                session.add(row)
            row.status = state.status
            row.attempts = state.attempts
            row.row_count = state.row_count
            session.commit()


class SqlFileRepo:
    """ingest_file repository: Events and Mentions fetch state (role: ingester_rw)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _state(row: IngestFile) -> FileState:
        return FileState(
            slot=row.slot,
            kind=row.kind,
            status=row.status,
            attempts=row.attempts,
            row_count=row.row_count,
        )

    def get(self, slot: str, kind: str) -> FileState | None:
        with Session(self._engine) as session:
            row = session.get(IngestFile, (slot, kind))
            return None if row is None else self._state(row)

    def pending(self, max_attempts: int) -> list[FileState]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(IngestFile)
                .where(IngestFile.status == "pending")
                .where(IngestFile.attempts < max_attempts)
                .order_by(IngestFile.slot, IngestFile.kind)
            ).all()
            return [self._state(r) for r in rows]

    def save(self, state: FileState) -> None:
        with Session(self._engine) as session:
            row = session.get(IngestFile, (state.slot, state.kind))
            if row is None:
                row = IngestFile(slot=state.slot, kind=state.kind, status=state.status)
                session.add(row)
            row.status = state.status
            row.attempts = state.attempts
            row.row_count = state.row_count
            session.commit()
