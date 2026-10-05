"""TC-1, TC-3, TC-4, TC-5: ingester cycle logic over fake ports."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

from newsdock_core.contracts import RawMessage
from newsdock_ingester.domain.cycle import Ingester, url_for
from newsdock_ingester.domain.index import parse_lastupdate
from newsdock_ingester.domain.ports import SlotState

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "packages" / "core" / "tests" / "fixtures" / "gkg_sample.tsv"
SLOT = "20261004081500"
BASE = "http://data.gdeltproject.org/gdeltv2"


def zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{SLOT}.gkg.csv", FIXTURE.read_bytes())
    return buf.getvalue()


class FakeSource:
    def __init__(self, index: str | None, files: dict[str, bytes]) -> None:
        self.index, self.files = index, files
        self.fetches: list[str] = []

    def fetch_index(self) -> str | None:
        return self.index

    def fetch_gkg(self, url: str) -> bytes | None:
        self.fetches.append(url)
        return self.files.get(url)


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []  # ("publish", key) / ("flush", "")

    def publish(self, key: str, message: RawMessage) -> None:
        json.loads(message.model_dump_json())  # serializable
        self.events.append(("publish", key))

    def flush(self) -> None:
        self.events.append(("flush", ""))


class FakeRepo:
    def __init__(self) -> None:
        self.states: dict[str, SlotState] = {}
        self.saves: list[tuple[str, str]] = []  # (slot, status)

    def get(self, slot: str) -> SlotState | None:
        return self.states.get(slot)

    def pending(self, max_attempts: int) -> list[SlotState]:
        return [
            s
            for s in self.states.values()
            if s.status == "pending" and s.attempts < max_attempts
        ]

    def save(self, state: SlotState) -> None:
        self.states[state.slot] = state
        self.saves.append((state.slot, state.status))


def make(
    files: dict[str, bytes] | None = None, index: str | None = None
) -> tuple[Ingester, FakeSource, FakePublisher, FakeRepo]:
    source = FakeSource(index, files or {})
    publisher, repo = FakePublisher(), FakeRepo()
    return Ingester(source, publisher, repo, base_url=BASE), source, publisher, repo


def good_md5() -> str:
    return hashlib.md5(zip_bytes()).hexdigest()


def test_parse_lastupdate_picks_the_gkg_line() -> None:
    text = (
        f"100 aa {BASE}/{SLOT}.export.CSV.zip\n"
        f"200 bb {BASE}/{SLOT}.mentions.CSV.zip\n"
        f"300 cc {BASE}/{SLOT}.gkg.csv.zip\n"
    )
    entry = parse_lastupdate(text)
    assert entry is not None
    assert (entry.slot, entry.md5, entry.url) == (
        SLOT,
        "cc",
        f"{BASE}/{SLOT}.gkg.csv.zip",
    )
    assert parse_lastupdate("garbage") is None


# TC-1: one raw message per row; published only after flush
def test_process_slot_publishes_one_message_per_row() -> None:
    ing, _, publisher, repo = make({url_for(BASE, SLOT): zip_bytes()})
    assert ing.process_slot(SLOT, md5=good_md5()) is True
    publishes = [e for e in publisher.events if e[0] == "publish"]
    assert len(publishes) == 20
    assert publishes[0][1] == f"{SLOT}:0" and publishes[-1][1] == f"{SLOT}:19"
    assert publisher.events[-1] == ("flush", "")  # flush after all publishes
    state = repo.states[SLOT]
    assert (state.status, state.row_count) == ("published", 20)
    # mark published only after the flush event existed
    assert repo.saves[-1] == (SLOT, "published")


def test_published_slot_is_skipped_unless_forced() -> None:
    ing, _, publisher, repo = make({url_for(BASE, SLOT): zip_bytes()})
    ing.process_slot(SLOT)
    n = len(publisher.events)
    assert ing.process_slot(SLOT) is True  # skip: no new events
    assert len(publisher.events) == n
    assert ing.process_slot(SLOT, force=True) is True  # R-10 test hook
    assert len(publisher.events) == n + 21


# TC-3: 404/empty → nothing published, pending, attempts+1, no crash
def test_missing_file_stays_pending_with_attempt_counted() -> None:
    ing, _, publisher, repo = make({})  # fetch_gkg returns None
    assert ing.process_slot(SLOT) is False
    assert publisher.events == []
    state = repo.states[SLOT]
    assert (state.status, state.attempts) == ("pending", 1)


def test_unreachable_index_is_quiet() -> None:
    ing, _, publisher, _ = make(index=None)
    ing.run_cycle()  # must not raise
    assert publisher.events == []


# TC-4: md5 mismatch handled exactly like a 404
def test_md5_mismatch_is_retry_later() -> None:
    ing, _, publisher, repo = make({url_for(BASE, SLOT): zip_bytes()})
    assert ing.process_slot(SLOT, md5="0" * 32) is False
    assert publisher.events == []
    assert repo.states[SLOT].attempts == 1


# TC-5: 4th failed attempt → failed, excluded from retries
def test_fourth_failure_marks_failed_and_stops_retrying() -> None:
    ing, source, _, repo = make(index=f"300 cc {BASE}/{SLOT}.gkg.csv.zip\n")
    repo.save(SlotState(slot=SLOT, status="pending", attempts=3, row_count=None))
    assert ing.process_slot(SLOT) is False
    assert repo.states[SLOT].status == "failed"
    fetches = len(source.fetches)
    ing.run_cycle()  # the failed slot (also the index's newest) is never retried
    assert len(source.fetches) == fetches


def test_run_cycle_registers_new_slot_and_processes_pending() -> None:
    files = {url_for(BASE, SLOT): zip_bytes()}
    ing, _, publisher, repo = make(
        files, index=f"300 {good_md5()} {url_for(BASE, SLOT)}\n"
    )
    repo.save(
        SlotState(slot="20261004080000", status="pending", attempts=2, row_count=None)
    )
    ing.run_cycle()
    assert repo.states[SLOT].status == "published"
    assert repo.states["20261004080000"].attempts == 3  # retried and failed again
