"""TC-4, TC-5, TC-7: events of a story's copies on the canonical article (Docker).

The sink writes a `derived` mention row for the canonical when a copy is mentioned
(ADR-0038). The read path is unchanged except that `mention_count` counts real rows.
Runs against a throwaway Postgres from `side_db`; the dev database is never touched.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_db.engine import make_engine
from newsdock_db.models import Event, Mention
from newsdock_db.testing import article
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
ADDED = datetime(2026, 11, 2, 11, tzinfo=UTC)


def _event(event_id: int, num_mentions: int) -> Event:
    return Event(
        event_id=event_id, event_date=date(2026, 11, 2), is_root=False,
        cameo_code="040", cameo_base="040", cameo_root="04", quad_class=1,
        goldstein=1.5, num_mentions=num_mentions, num_sources=2, num_articles=3,
        avg_tone=-2.5, date_added=ADDED, source_url=f"https://e.com/{event_id}",
        source_url_hash="K",
    )  # fmt: skip


def _mention(event_id: int, url_hash: str, *, derived: bool = False) -> Mention:
    return Mention(
        event_id=event_id, url_hash=url_hash, url=f"https://e.com/{url_hash}",
        mention_time=ADDED, derived=derived,
    )  # fmt: skip


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE events, mentions"))
    with Session(eng) as session:
        session.add(article("K", "A syndicated story", model=None))
        session.commit()
        session.add_all([_event(50, 10), _event(51, 8), _event(52, 6), _event(53, 4)])
        session.add_all(
            [
                # 50: three real mentions (the copy X and two outlets) + the link
                _mention(50, "X"), _mention(50, "O1"), _mention(50, "O2"),
                _mention(50, "K", derived=True),
                # 51: the canonical and its copy both mention it for real: one row
                _mention(51, "K"), _mention(51, "X"),
                # 52, 53: only the copy mentions them, so only the link reaches K
                _mention(52, "X"), _mention(52, "K", derived=True),
                _mention(53, "X"), _mention(53, "K", derived=True),
            ]
        )  # fmt: skip
        session.commit()
    yield eng
    eng.dispose()


def _events(engine: Engine, cap: int = 20) -> list[Any]:
    repo = SqlArticleRepo(engine, events_per_article=cap)
    found = repo.summaries(["K"], include=("events",))["K"].events
    return list(found or [])


def test_mention_count_counts_real_mentions_only(engine: Engine) -> None:  # TC-4
    by_id = {e.event_id: e for e in _events(engine)}
    assert by_id[50].mention_count == 3  # X, O1, O2; the derived row is not counted
    assert by_id[52].mention_count == 1
    assert by_id[53].mention_count == 1


def test_an_event_of_the_canonical_and_its_copy_appears_once(
    engine: Engine,
) -> None:  # TC-5
    events = _events(engine)
    assert [e.event_id for e in events].count(51) == 1
    assert {e.event_id: e.mention_count for e in events}[51] == 2


def test_events_found_through_copies_are_capped_and_ordered(
    engine: Engine,
) -> None:  # TC-7
    assert [e.event_id for e in _events(engine)] == [50, 51, 52, 53]
    assert [e.event_id for e in _events(engine, cap=2)] == [50, 51]


def test_the_detail_carries_them_too(engine: Engine) -> None:  # AC-9 (repo)
    detail = SqlArticleRepo(engine, events_per_article=20).get("K")
    assert detail is not None
    assert [e.event_id for e in detail.events] == [50, 51, 52, 53]
