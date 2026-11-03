"""TC-24 (AC-4, AC-5, AC-7, AC-9): GDELT Events and Mentions through the whole chain.

Real code end to end, no Kafka: the ingester cycle (fake GDELT source) -> processor
`route()` -> sink writers -> the API repo, on a throwaway Postgres from `side_postgres`
(own compose project and free port, so it is safe next to a running dev stack). Lives
in infra/scripts/tests because it crosses apps, which app-local tests must not do
(DR-7).

Phase 1: the Events file is not available yet (the 404 quirk). GKG and Mentions flow,
and the article has no events (a mention without its event is kept, hidden). Phase 2:
the file shows up on the next cycle, only it is published, and the article now returns
the event.
"""

import hashlib
import io
import zipfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_core.contracts import DlqMessage, RawMessage
from newsdock_core.urls import url_hash
from newsdock_db.engine import make_engine
from newsdock_db.models import Event, Mention
from newsdock_db.testing import side_postgres
from newsdock_ingester.domain.cycle import Ingester, url_for
from newsdock_ingester.domain.ports import FileState, SlotState
from newsdock_processor.domain.route import route
from newsdock_sink.adapters.db import SqlArticleWriter, SqlGdeltWriter
from newsdock_sink.domain.gdelt import process_events, process_mentions
from newsdock_sink.domain.writer import SinkItem, process_batch
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
SLOT = "20261102110000"
BASE = "http://x"
TOPICS = {"clean": "c", "dlq": "d", "events": "e", "mentions": "m"}
MEMBER = {"gkg": "gkg.csv", "events": "export.CSV", "mentions": "mentions.CSV"}
NAME = {
    "gkg": f"{SLOT}.gkg.csv.zip",
    "events": f"{SLOT}.export.CSV.zip",
    "mentions": f"{SLOT}.mentions.CSV.zip",
}


@pytest.fixture(scope="module")
def side_db() -> Iterator[tuple[str, str]]:
    """A throwaway Postgres (own compose project, free port); DATABASE_URL points at
    it for the module. The name `side_db` is what the dev-stack guard looks for."""
    mp = pytest.MonkeyPatch()
    with side_postgres("newsdock-side-events-pipeline") as (url, dsn):
        mp.setenv("DATABASE_URL", url)
        try:
            yield url, dsn
        finally:
            mp.undo()


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE events, mentions"))
    yield eng
    eng.dispose()


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


def _zip(kind: str, lines: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{SLOT}.{MEMBER[kind]}", "\n".join(lines))
    return buf.getvalue()


def _with(line: str, index: int, value: str) -> str:
    columns = line.split("\t")
    columns[index] = value
    return "\t".join(columns)


class Data:
    """Three files of one slot whose article, event and mention line up on one URL."""

    def __init__(self) -> None:
        events = _lines("events_sample.tsv")
        first = events[0].split("\t")
        self.event_id, self.url = int(first[0]), first[60]
        self.article_id = url_hash(self.url)
        mentions = _lines("mentions_sample.tsv")
        link = _with(_with(mentions[0], 0, str(self.event_id)), 5, self.url)
        gkg = _lines("gkg_sample.tsv")[:3]
        gkg[0] = _with(gkg[0], 4, self.url)
        self.lines = {"gkg": gkg, "events": events, "mentions": [*mentions, link]}
        self.zips = {kind: _zip(kind, rows) for kind, rows in self.lines.items()}

    def unique_events(self) -> int:
        return len({line.split("\t")[0] for line in self.lines["events"]})

    def unique_mentions(self) -> int:
        return len(
            {
                (int(c[0]), url_hash(c[5]))
                for c in (line.split("\t") for line in self.lines["mentions"])
            }
        )

    def index(self) -> str:
        return "".join(
            f"1 {hashlib.md5(self.zips[kind]).hexdigest()} {BASE}/{NAME[kind]}\n"
            for kind in ("events", "mentions", "gkg")
        )


class Source:
    def __init__(self, data: Data) -> None:
        self.data = data
        self.available = {"gkg", "mentions"}  # the Events file is "404" at first

    def fetch_index(self) -> str | None:
        return self.data.index()

    def fetch(self, url: str) -> bytes | None:
        for kind in self.available:
            if url == url_for(BASE, SLOT, kind):
                return self.data.zips[kind]
        return None


class Collect:
    def __init__(self) -> None:
        self.messages: list[RawMessage] = []

    def publish(self, key: str, message: RawMessage) -> None:
        self.messages.append(message)

    def flush(self) -> None:
        pass


class SlotRepo:
    def __init__(self) -> None:
        self.states: dict[str, SlotState] = {}

    def get(self, slot: str) -> SlotState | None:
        return self.states.get(slot)

    def pending(self, max_attempts: int) -> list[SlotState]:
        return [s for s in self.states.values() if s.status == "pending"]

    def save(self, state: SlotState) -> None:
        self.states[state.slot] = state


class FileRepo:
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


class NoDlq:
    def send(self, key: str, message: DlqMessage) -> None:
        raise AssertionError(f"unexpected dead-letter message {key}: {message.reason}")


class Chain:
    """The ingester plus the processor and sink steps, one `cycle()` at a time."""

    def __init__(self, engine: Engine, data: Data) -> None:
        self.source = Source(data)
        self.collect = Collect()
        self.slots, self.files = SlotRepo(), FileRepo()
        self.ingester = Ingester(
            self.source,
            self.collect,
            self.slots,
            base_url=BASE,
            max_attempts=4,
            file_repo=self.files,
            file_kinds=("events", "mentions"),
        )
        self.articles = SqlArticleWriter(engine)
        self.gdelt = SqlGdeltWriter(engine)

    def cycle(self) -> list[RawMessage]:
        """One ingest cycle, then route and write what it published; returns it."""
        self.collect.messages = []
        self.ingester.run_cycle()
        published = list(self.collect.messages)
        self.write(published)
        return published

    def write(self, published: list[RawMessage]) -> None:
        by_topic: dict[str, list[SinkItem]] = {}
        for message in published:
            routed = route(
                message,
                TOPICS["clean"],
                TOPICS["dlq"],
                events_topic=TOPICS["events"],
                mentions_topic=TOPICS["mentions"],
            )
            assert routed.topic != TOPICS["dlq"], routed.value
            by_topic.setdefault(routed.topic, []).append(
                SinkItem(key=routed.key, value=routed.value.encode())
            )
        process_batch(
            by_topic.get(TOPICS["clean"], []),
            self.articles,
            NoDlq(),
            window=timedelta(hours=48),
        )
        process_events(by_topic.get(TOPICS["events"], []), self.gdelt, NoDlq())
        process_mentions(by_topic.get(TOPICS["mentions"], []), self.gdelt, NoDlq())


def _count(engine: Engine, model: Any) -> int:
    with Session(engine) as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _kinds(messages: list[RawMessage]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in messages:
        counts[message.kind] = counts.get(message.kind, 0) + 1
    return counts


def test_events_and_mentions_flow_through_the_whole_chain(engine: Engine) -> None:
    data = Data()
    chain = Chain(engine, data)
    repo = SqlArticleRepo(engine)

    # Phase 1: the Events file is not available yet (AC-4)
    first = chain.cycle()
    lines = data.lines
    assert _kinds(first) == {
        "gkg": len(lines["gkg"]),
        "mentions": len(lines["mentions"]),
    }
    assert chain.slots.states[SLOT].status == "published"
    assert chain.files.states[(SLOT, "mentions")].status == "published"
    events_state = chain.files.states[(SLOT, "events")]
    assert (events_state.status, events_state.attempts) == ("pending", 1)
    assert _count(engine, Event) == 0
    # repeated (event, URL) pairs are one row each (AC-5)
    assert _count(engine, Mention) == data.unique_mentions()
    assert data.unique_mentions() < len(lines["mentions"])
    article = repo.get(data.article_id)
    assert article is not None
    assert article.events == []  # a mention without its event is kept but hidden (AC-7)

    # Phase 2: the file shows up; only it is published (AC-4)
    chain.source.available.add("events")
    second = chain.cycle()
    assert _kinds(second) == {"events": len(lines["events"])}
    assert chain.files.states[(SLOT, "events")].status == "published"
    assert _count(engine, Event) == data.unique_events()
    article = repo.get(data.article_id)
    assert article is not None
    assert [e.event_id for e in article.events] == [data.event_id]  # AC-9
    assert article.events[0].mention_count >= 1
    listed = repo.search(
        time_from=None, time_to=None, theme=None, domain=None, text=None, limit=50,
        include=("events",),
    )  # fmt: skip
    found = {a.article_id: a for a in listed}
    assert [e.event_id for e in found[data.article_id].events or []] == [data.event_id]

    # Replay: the same messages again change nothing (AC-5)
    before = (_count(engine, Event), _count(engine, Mention))
    chain.write(first + second)
    assert (_count(engine, Event), _count(engine, Mention)) == before

    # A later cycle publishes nothing new: every file is done
    assert chain.cycle() == []
