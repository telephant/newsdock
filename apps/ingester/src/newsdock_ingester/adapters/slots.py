"""ingest_slot repository over newsdock_db (role: ingester_rw)."""

from newsdock_db.models import IngestSlot
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from newsdock_ingester.domain.ports import SlotState


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
