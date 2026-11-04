"""Ingest cycle (design-detail §2, §3): poll index, publish rows, track file state.

404, empty body and md5 mismatch are "retry later", never errors (spec §3).
A slot is `published` only after every row is flushed to Kafka; the 4th failed
attempt marks it `failed` (R-8). `process_slot(slot, force=True)` is the AC-3
test hook (R-10).

Since M3c `events-mentions` (ADR-0032) a slot also has an Events and a Mentions file.
Each has its own state in `ingest_file` and is handled after GKG, so a missing file
never blocks GKG or the other file (AC-4).
"""

import hashlib
import io
import logging
import zipfile

from newsdock_core.contracts import Kind, RawMessage

from newsdock_ingester.domain.index import parse_index
from newsdock_ingester.domain.ports import (
    FileRepo,
    FileState,
    GdeltSource,
    RawPublisher,
    SlotRepo,
    SlotState,
)

logger = logging.getLogger(__name__)

_SUFFIX: dict[str, str] = {
    "gkg": "gkg.csv.zip",
    "events": "export.CSV.zip",
    "mentions": "mentions.CSV.zip",
}


def url_for(base_url: str, slot: str, kind: str = "gkg") -> str:
    return f"{base_url}/{slot}.{_SUFFIX[kind]}"


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
        max_attempts: int,
        file_repo: FileRepo | None = None,
        file_kinds: tuple[str, ...] = (),
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._repo = repo
        self._base_url = base_url
        self._max_attempts = max_attempts
        self._file_repo = file_repo
        self._file_kinds = file_kinds if file_repo is not None else ()

    def run_cycle(self) -> None:
        """One poll: register the newest slot and files, process what is pending."""
        index_md5: dict[tuple[str, str], str] = {}
        index = self._source.fetch_index()
        if index is None:
            logger.warning("lastupdate.txt unreachable; retrying next cycle")
        else:
            for entry in parse_index(index):
                index_md5[(entry.slot, entry.kind)] = entry.md5
                if entry.kind == "gkg":
                    if self._repo.get(entry.slot) is None:
                        self._repo.save(SlotState(slot=entry.slot, status="pending"))
                elif entry.kind in self._file_kinds:
                    self._register_file(entry.slot, entry.kind)
        for state in self._repo.pending(self._max_attempts):
            self.process_slot(state.slot, md5=index_md5.get((state.slot, "gkg")))
        if self._file_repo is not None:
            for file_state in self._file_repo.pending(self._max_attempts):
                if file_state.kind in self._file_kinds:
                    self.process_file(
                        file_state.slot,
                        file_state.kind,
                        md5=index_md5.get((file_state.slot, file_state.kind)),
                    )

    def _register_file(self, slot: str, kind: str) -> None:
        """File rows exist only for slots listed while the feature is on."""
        assert self._file_repo is not None
        if self._file_repo.get(slot, kind) is None:
            self._file_repo.save(FileState(slot=slot, kind=kind, status="pending"))

    def _download(self, slot: str, kind: str, md5: str | None) -> list[str] | None:
        """The rows of one file, or None for 404, empty body, bad md5 or a bad zip."""
        data = self._source.fetch(url_for(self._base_url, slot, kind))
        if data is not None and md5 is not None:
            if hashlib.md5(data).hexdigest() != md5:
                logger.warning("%s %s: md5 mismatch, treating as 404", kind, slot)
                data = None
        return _rows(data) if data else None

    def _publish_rows(self, slot: str, kind: str, rows: list[str]) -> None:
        for row_no, line in enumerate(rows):
            key = f"{slot}:{row_no}" if kind == "gkg" else f"{slot}:{kind}:{row_no}"
            self._publisher.publish(
                key,
                RawMessage(slot=slot, row_no=row_no, line=line, kind=_kind(kind)),
            )
        self._publisher.flush()

    def process_slot(
        self, slot: str, *, md5: str | None = None, force: bool = False
    ) -> bool:
        """Fetch and publish one slot. Returns True when the slot is published."""
        state = self._repo.get(slot) or SlotState(slot=slot, status="pending")
        if state.status == "published" and not force:
            return True

        rows = self._download(slot, "gkg", md5)
        if rows is None:
            state.attempts += 1
            if state.attempts >= self._max_attempts:
                state.status = "failed"
                logger.error("slot %s: %d attempts, giving up", slot, state.attempts)
            else:
                logger.info("slot %s: not available, retry next cycle", slot)
            self._repo.save(state)
            return False

        self._publish_rows(slot, "gkg", rows)
        state.status = "published"
        state.row_count = len(rows)
        self._repo.save(state)
        logger.info("slot %s: published %d rows", slot, len(rows))
        return True

    def process_file(self, slot: str, kind: str, *, md5: str | None = None) -> bool:
        """Fetch and publish the Events or Mentions file of a slot; own retry state."""
        assert self._file_repo is not None
        state = self._file_repo.get(slot, kind) or FileState(
            slot=slot, kind=kind, status="pending"
        )
        if state.status == "published":
            return True

        rows = self._download(slot, kind, md5)
        if rows is None:
            state.attempts += 1
            if state.attempts >= self._max_attempts:
                state.status = "failed"
                logger.error(
                    "%s %s: %d attempts, giving up", kind, slot, state.attempts
                )
            else:
                logger.info("%s %s: not available, retry next cycle", kind, slot)
            self._file_repo.save(state)
            return False

        self._publish_rows(slot, kind, rows)
        state.status = "published"
        state.row_count = len(rows)
        self._file_repo.save(state)
        logger.info("%s %s: published %d rows", kind, slot, len(rows))
        return True


def _kind(kind: str) -> Kind:
    if kind == "events":
        return "events"
    if kind == "mentions":
        return "mentions"
    return "gkg"
