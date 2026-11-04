"""TC-7, TC-8 (AC-4, ADR-0032): Events and Mentions files with their own fetch state."""

import hashlib
import io
import zipfile
from pathlib import Path

from newsdock_core.contracts import RawMessage
from newsdock_ingester.domain.cycle import Ingester, url_for
from newsdock_ingester.domain.index import parse_index, parse_lastupdate
from newsdock_ingester.domain.ports import FileState, SlotState

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
SLOT = "20261102110000"
BASE = "http://data.gdeltproject.org/gdeltv2"
MEMBER = {"gkg": "gkg.csv", "events": "export.CSV", "mentions": "mentions.CSV"}
SAMPLE = {
    "gkg": "gkg_sample.tsv",
    "events": "events_sample.tsv",
    "mentions": "mentions_sample.tsv",
}
ROWS = {"gkg": 20, "events": 33, "mentions": 60}


def zip_for(kind: str, slot: str = SLOT) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{slot}.{MEMBER[kind]}", (FIXTURES / SAMPLE[kind]).read_bytes())
    return buf.getvalue()


def index_text(slot: str = SLOT, *, md5: dict[str, str] | None = None) -> str:
    md5 = md5 or {}
    names = {
        "events": f"{slot}.export.CSV.zip",
        "mentions": f"{slot}.mentions.CSV.zip",
        "gkg": f"{slot}.gkg.csv.zip",
    }
    return "".join(
        f"100 {md5.get(kind, good_md5(kind))} {BASE}/{name}\n"
        for kind, name in names.items()
    )


def good_md5(kind: str) -> str:
    return hashlib.md5(zip_for(kind)).hexdigest()


class FakeSource:
    def __init__(self, index: str | None, files: dict[str, bytes]) -> None:
        self.index, self.files = index, files
        self.fetches: list[str] = []

    def fetch_index(self) -> str | None:
        return self.index

    def fetch(self, url: str) -> bytes | None:
        self.fetches.append(url)
        return self.files.get(url)


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, RawMessage]] = []

    def publish(self, key: str, message: RawMessage) -> None:
        self.messages.append((key, message))

    def flush(self) -> None:
        pass


class FakeSlotRepo:
    def __init__(self) -> None:
        self.states: dict[str, SlotState] = {}

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


class FakeFileRepo:
    def __init__(self) -> None:
        self.states: dict[tuple[str, str], FileState] = {}

    def get(self, slot: str, kind: str) -> FileState | None:
        return self.states.get((slot, kind))

    def pending(self, max_attempts: int) -> list[FileState]:
        return [
            s
            for s in self.states.values()
            if s.status == "pending" and s.attempts < max_attempts
        ]

    def save(self, state: FileState) -> None:
        self.states[(state.slot, state.kind)] = state


def make(
    available: tuple[str, ...] = ("gkg", "events", "mentions"),
    *,
    index: str | None = None,
    kinds: tuple[str, ...] = ("events", "mentions"),
    max_attempts: int = 4,
) -> tuple[Ingester, FakeSource, FakePublisher, FakeSlotRepo, FakeFileRepo]:
    files = {url_for(BASE, SLOT, kind): zip_for(kind) for kind in available}
    source = FakeSource(index if index is not None else index_text(), files)
    publisher, slots, file_repo = FakePublisher(), FakeSlotRepo(), FakeFileRepo()
    ingester = Ingester(
        source,
        publisher,
        slots,
        base_url=BASE,
        max_attempts=max_attempts,
        file_repo=file_repo,
        file_kinds=kinds,
    )
    return ingester, source, publisher, slots, file_repo


def test_index_lists_three_files_and_gkg_parse_is_unchanged() -> None:
    entries = parse_index(index_text())
    assert {(e.kind, e.slot) for e in entries} == {
        ("events", SLOT),
        ("mentions", SLOT),
        ("gkg", SLOT),
    }
    gkg = parse_lastupdate(index_text())
    assert gkg is not None and gkg.slot == SLOT
    assert gkg.url.endswith(f"{SLOT}.gkg.csv.zip")
    assert parse_index("garbage") == []


def test_url_for_each_kind_and_gkg_default() -> None:
    assert url_for(BASE, SLOT) == f"{BASE}/{SLOT}.gkg.csv.zip"
    assert url_for(BASE, SLOT, "events") == f"{BASE}/{SLOT}.export.CSV.zip"
    assert url_for(BASE, SLOT, "mentions") == f"{BASE}/{SLOT}.mentions.CSV.zip"


def test_all_three_files_are_published_with_their_kind_and_key() -> None:
    ing, _, publisher, slots, files = make()
    ing.run_cycle()
    assert slots.states[SLOT].status == "published"
    for kind in ("events", "mentions"):
        state = files.states[(SLOT, kind)]
        assert (state.status, state.row_count) == ("published", ROWS[kind])
        sent = [(k, m) for k, m in publisher.messages if m.kind == kind]
        assert len(sent) == ROWS[kind]
        assert sent[0][0] == f"{SLOT}:{kind}:0"
        assert sent[0][1].slot == SLOT and sent[0][1].row_no == 0
    gkg_keys = [k for k, m in publisher.messages if m.kind == "gkg"]
    assert len(gkg_keys) == 20 and gkg_keys[0] == f"{SLOT}:0"


# TC-7: a missing Events file never blocks GKG or Mentions
def test_events_404_leaves_only_events_pending() -> None:
    ing, _, publisher, slots, files = make(available=("gkg", "mentions"))
    ing.run_cycle()
    assert slots.states[SLOT].status == "published"
    assert files.states[(SLOT, "mentions")].status == "published"
    events = files.states[(SLOT, "events")]
    assert (events.status, events.attempts) == ("pending", 1)
    assert not [m for _, m in publisher.messages if m.kind == "events"]
    assert len([m for _, m in publisher.messages if m.kind == "gkg"]) == 20


# TC-8: each file retries on its own and gives up after max_attempts
def test_events_fails_after_four_attempts_without_touching_gkg() -> None:
    ing, source, _, slots, files = make(available=("gkg", "mentions"))
    for _ in range(5):
        ing.run_cycle()
    events = files.states[(SLOT, "events")]
    assert (events.status, events.attempts) == ("failed", 4)
    assert slots.states[SLOT].status == "published"
    assert source.fetches.count(url_for(BASE, SLOT, "events")) == 4


def test_a_late_events_file_is_published_on_a_later_cycle() -> None:
    ing, source, publisher, _, files = make(available=("gkg", "mentions"))
    ing.run_cycle()
    source.files[url_for(BASE, SLOT, "events")] = zip_for("events")
    ing.run_cycle()
    assert files.states[(SLOT, "events")].status == "published"
    assert len([m for _, m in publisher.messages if m.kind == "events"]) == 33


def test_md5_mismatch_on_a_file_is_retry_later() -> None:
    index = index_text(md5={"events": "0" * 32, "mentions": good_md5("mentions")})
    ing, _, publisher, _, files = make(index=index)
    ing.run_cycle()
    assert files.states[(SLOT, "events")].status == "pending"
    assert files.states[(SLOT, "mentions")].status == "published"
    assert not [m for _, m in publisher.messages if m.kind == "events"]


def test_disabled_kind_is_neither_registered_nor_fetched() -> None:
    ing, source, _, _, files = make(kinds=("mentions",))
    ing.run_cycle()
    assert (SLOT, "events") not in files.states
    assert url_for(BASE, SLOT, "events") not in source.fetches
    assert files.states[(SLOT, "mentions")].status == "published"


def test_no_file_repo_behaves_as_before() -> None:
    files = {url_for(BASE, SLOT): zip_for("gkg")}
    source = FakeSource(index_text(), files)
    publisher, slots = FakePublisher(), FakeSlotRepo()
    Ingester(source, publisher, slots, base_url=BASE, max_attempts=4).run_cycle()
    assert slots.states[SLOT].status == "published"
    assert source.fetches == [url_for(BASE, SLOT)]


def test_older_slots_without_file_rows_are_not_backfilled() -> None:
    ing, source, _, slots, files = make()
    older = "20261102100000"
    slots.save(SlotState(slot=older, status="published", row_count=1))
    ing.run_cycle()
    assert all(older not in url for url in source.fetches)
    assert {slot for slot, _ in files.states} == {SLOT}
