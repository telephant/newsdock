"""Ingest cycle (design-detail §2): poll index, publish rows, track slot state.

404, empty body and md5 mismatch are "retry later", never errors (spec §3).
A slot is `published` only after every row is flushed to Kafka; the 4th failed
attempt marks it `failed` (R-8). `process_slot(slot, force=True)` is the AC-3
test hook (R-10).
"""

import hashlib
import io
import logging
import zipfile

from newsdock_core.contracts import RawMessage

from newsdock_ingester.domain.index import parse_lastupdate
from newsdock_ingester.domain.ports import (
    GdeltSource,
    RawPublisher,
    SlotRepo,
    SlotState,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4


def url_for(base_url: str, slot: str) -> str:
    return f"{base_url}/{slot}.gkg.csv.zip"


def _rows(zip_data: bytes) -> list[str] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            name = zf.namelist()[0]
            return zf.read(name).decode("utf-8", errors="replace").splitlines()
    except (zipfile.BadZipFile, IndexError):
        return None


class Ingester:
    def __init__(
        self,
        source: GdeltSource,
        publisher: RawPublisher,
        repo: SlotRepo,
        *,
        base_url: str,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._repo = repo
        self._base_url = base_url
        self._max_attempts = max_attempts

    def run_cycle(self) -> None:
        """One poll: register the newest slot, process it and every pending slot."""
        index_md5: dict[str, str] = {}
        index = self._source.fetch_index()
        if index is None:
            logger.warning("lastupdate.txt unreachable; retrying next cycle")
        else:
            entry = parse_lastupdate(index)
            if entry is not None:
                index_md5[entry.slot] = entry.md5
                if self._repo.get(entry.slot) is None:
                    self._repo.save(SlotState(slot=entry.slot, status="pending"))
        for state in self._repo.pending(self._max_attempts):
            self.process_slot(state.slot, md5=index_md5.get(state.slot))

    def process_slot(
        self, slot: str, *, md5: str | None = None, force: bool = False
    ) -> bool:
        """Fetch and publish one slot. Returns True when the slot is published."""
        state = self._repo.get(slot) or SlotState(slot=slot, status="pending")
        if state.status == "published" and not force:
            return True

        data = self._source.fetch_gkg(url_for(self._base_url, slot))
        if data is not None and md5 is not None:
            if hashlib.md5(data).hexdigest() != md5:
                logger.warning("slot %s: md5 mismatch, treating as 404", slot)
                data = None
        rows = _rows(data) if data else None
        if rows is None:
            state.attempts += 1
            if state.attempts >= self._max_attempts:
                state.status = "failed"
                logger.error("slot %s: %d attempts, giving up", slot, state.attempts)
            else:
                logger.info("slot %s: not available, retry next cycle", slot)
            self._repo.save(state)
            return False

        for row_no, line in enumerate(rows):
            self._publisher.publish(
                f"{slot}:{row_no}", RawMessage(slot=slot, row_no=row_no, line=line)
            )
        self._publisher.flush()
        state.status = "published"
        state.row_count = len(rows)
        self._repo.save(state)
        logger.info("slot %s: published %d rows", slot, len(rows))
        return True
