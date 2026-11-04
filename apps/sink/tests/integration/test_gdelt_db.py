"""TC-9, TC-10, TC-11, TC-12: Events and Mentions upserts on real Postgres (Docker).

Runs against a throwaway Postgres from the `side_db` fixture (own compose project,
free port), so the dev stack's database is never touched.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_core.contracts import CleanEvent, CleanMention, DlqMessage
from newsdock_core.events import parse_event_row
from newsdock_core.mentions import parse_mention_row
from newsdock_db.engine import make_engine
from newsdock_db.models import Event, Mention
from newsdock_sink.adapters.db import SqlGdeltWriter
from newsdock_sink.domain.gdelt import process_events, process_mentions
from newsdock_sink.domain.writer import SinkItem
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
SLOT = "20261102110000"


class NullDlq:
    def __init__(self) -> None:
        self.sent: list[DlqMessage] = []

    def send(self, key: str, message: DlqMessage) -> None:
        self.sent.append(message)


@pytest.fixture(scope="module")
def engine_url(side_db: tuple[str, str]) -> Iterator[str]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    yield side_db[0]


@pytest.fixture()
def writer(engine_url: str) -> Iterator[SqlGdeltWriter]:
    engine = make_engine(engine_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE events, mentions"))
    yield SqlGdeltWriter(engine)
    engine.dispose()


def events() -> list[CleanEvent]:
    out = []
    for n, line in enumerate((FIXTURES / "events_sample.tsv").read_text().splitlines()):
        parsed = parse_event_row(slot=SLOT, row_no=n, line=line)
        assert isinstance(parsed, CleanEvent)
        out.append(parsed)
    return out


def mentions() -> list[CleanMention]:
    out = []
    for n, line in enumerate(
        (FIXTURES / "mentions_sample.tsv").read_text().splitlines()
    ):
        parsed = parse_mention_row(slot=SLOT, row_no=n, line=line)
        assert isinstance(parsed, CleanMention)
        out.append(parsed)
    return out


def items(models: list[CleanEvent] | list[CleanMention]) -> list[SinkItem]:
    return [
        SinkItem(key=str(n), value=m.model_dump_json().encode())
        for n, m in enumerate(models)
    ]


def count(engine_url: str, model: type[Event] | type[Mention]) -> int:
    engine = make_engine(engine_url)
    with Session(engine) as session:
        total = session.scalar(select(func.count()).select_from(model))
    engine.dispose()
    return int(total or 0)


# TC-9 (AC-5): replaying the same batches changes nothing
def test_replay_leaves_both_tables_unchanged(
    writer: SqlGdeltWriter, engine_url: str
) -> None:
    ev, mn = events(), mentions()
    process_events(items(ev), writer, NullDlq())
    process_mentions(items(mn), writer, NullDlq())
    first = (count(engine_url, Event), count(engine_url, Mention))
    assert first == (33, 59)  # the repeated mention pair is one row
    process_events(items(ev), writer, NullDlq())
    process_mentions(items(mn), writer, NullDlq())
    assert (count(engine_url, Event), count(engine_url, Mention)) == first


# TC-10 (AC-5): duplicate keys in one batch do not error
def test_duplicate_keys_in_one_batch_are_written_once(
    writer: SqlGdeltWriter, engine_url: str
) -> None:
    ev, mn = events(), mentions()
    dlq = NullDlq()
    process_events(items([ev[0], ev[0], ev[1]]), writer, dlq)
    process_mentions(items([mn[0], mn[1]]), writer, dlq)  # same (event, URL)
    assert count(engine_url, Event) == 2
    assert count(engine_url, Mention) == 1
    assert dlq.sent == []


# TC-11 (AC-6): a newer date_added replaces the row, an older one is ignored
def test_newer_event_replaces_and_older_is_ignored(
    writer: SqlGdeltWriter, engine_url: str
) -> None:
    base = events()[0].model_copy(
        update={"num_mentions": 3, "date_added": datetime(2026, 11, 2, 11, tzinfo=UTC)}
    )
    later = base.model_copy(
        update={
            "num_mentions": 7,
            "date_added": base.date_added + timedelta(minutes=15),
        }
    )
    earlier = base.model_copy(
        update={
            "num_mentions": 1,
            "date_added": base.date_added - timedelta(minutes=15),
        }
    )
    process_events(items([base]), writer, NullDlq())
    process_events(items([later]), writer, NullDlq())
    process_events(items([earlier]), writer, NullDlq())
    engine = make_engine(engine_url)
    with Session(engine) as session:
        rows = session.scalars(select(Event)).all()
    engine.dispose()
    assert len(rows) == 1 and rows[0].num_mentions == 7
    assert rows[0].date_added == later.date_added


# TC-12 (AC-7): a mention stored before its event is kept and joins once the event lands
def test_mention_before_event_is_kept_and_joins_later(
    writer: SqlGdeltWriter, engine_url: str
) -> None:
    ev, mn = events()[0], mentions()[0]
    mention = mn.model_copy(update={"event_id": ev.event_id})
    process_mentions(items([mention]), writer, NullDlq())
    join = text(
        "SELECT count(*) FROM mentions m JOIN events e USING (event_id) "
        "WHERE m.url_hash = :h"
    )
    engine = make_engine(engine_url)
    with Session(engine) as session:
        assert count(engine_url, Mention) == 1
        assert session.execute(join, {"h": mention.url_hash}).scalar_one() == 0
        process_events(items([ev]), writer, NullDlq())
        assert session.execute(join, {"h": mention.url_hash}).scalar_one() == 1
    engine.dispose()


def test_poison_row_is_dead_lettered_and_the_rest_are_stored(
    writer: SqlGdeltWriter, engine_url: str
) -> None:
    ev = events()
    poison = ev[0].model_copy(update={"source_url": "https://x/\x00bad"})  # NUL byte
    dlq = NullDlq()
    result = process_events(items([poison, ev[1], ev[2]]), writer, dlq)
    assert (result.written, result.dlq) == (2, 1)
    assert count(engine_url, Event) == 2
    assert dlq.sent[0].kind == "events"
