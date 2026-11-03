"""TC-14, TC-16, TC-17 (repo half), TC-19: events per article on real Postgres (Docker).

Rows come in through the tables directly. An article's events are those it is
mentioned in (`mentions.url_hash`), capped and ordered, each with `mention_count`.
Runs against a throwaway Postgres from `side_db`; the dev database is never touched.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_db.engine import make_engine
from newsdock_db.models import Event, Mention
from newsdock_db.testing import article
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
ADDED = datetime(2026, 11, 2, 11, tzinfo=UTC)


def _event(event_id: int, num_mentions: int, **kw: Any) -> Event:
    values: dict[str, Any] = {
        "event_id": event_id, "event_date": date(2026, 11, 2), "is_root": False,
        "cameo_code": "040", "cameo_base": "040", "cameo_root": "04",
        "quad_class": 1, "goldstein": 1.5, "num_mentions": num_mentions,
        "num_sources": 2, "num_articles": 3, "avg_tone": -2.5,
        "actor1_code": "GOV", "actor1_name": "PRESIDENT", "actor1_country": "FR",
        "actor1_type": "GOV", "geo_name": "Paris, France", "geo_country": "FR",
        "geo_adm1": "FR11", "geo_lat": 48.85, "geo_lon": 2.35,
        "date_added": ADDED, "source_url": f"https://e.com/{event_id}",
        "source_url_hash": "A",
    }  # fmt: skip
    values.update(kw)
    return Event(**values)


def _mention(event_id: int, url_hash: str, minutes: int = 0) -> Mention:
    return Mention(
        event_id=event_id, url_hash=url_hash, url=f"https://e.com/{url_hash}",
        mention_time=ADDED + timedelta(minutes=minutes),
    )  # fmt: skip


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE events, mentions"))
    with Session(eng) as session:
        session.add_all(
            [
                article("A", "Protest in Paris", domain="a.com"),
                article("B", "Quiet day", domain="b.com"),  # no event at all
                article("C", "Many events", domain="c.com"),
                article("D", "Mention only", domain="d.com"),
            ]
        )
        session.commit()
        session.add_all(
            [
                _event(1, num_mentions=5),
                _event(2, num_mentions=9, actor1_code=None, actor1_name=None,
                       geo_name=None, geo_country=None, geo_adm1=None,
                       geo_lat=None, geo_lon=None),
                _event(3, num_mentions=9),  # ties with event 2: event_id decides
            ]
        )  # fmt: skip
        session.add_all(
            [
                _mention(1, "A"), _mention(2, "A"), _mention(3, "A"),
                _mention(1, "X1"), _mention(1, "X2"),  # two more outlets on event 1
                _mention(2, "X3"),
                _mention(99, "D"),  # mention of an event we never stored
            ]
        )  # fmt: skip
        # article C is mentioned in 25 events with growing num_mentions
        for n in range(100, 125):
            session.add(_event(n, num_mentions=n, source_url_hash="C"))
            session.add(_mention(n, "C"))
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture()
def repo(engine: Engine) -> SqlArticleRepo:
    return SqlArticleRepo(engine, events_per_article=20)


def _search(repo: SqlArticleRepo, **kw: Any) -> list[Any]:
    args: dict[str, Any] = {
        "time_from": None, "time_to": None, "theme": None, "domain": None,
        "text": None, "limit": 50,
    }  # fmt: skip
    args.update(kw)
    return repo.search(**args)


def _by_id(rows: list[Any]) -> dict[str, Any]:
    return {r.article_id: r for r in rows}


# TC-14: events of an article, with the curated fields and mention_count
def test_search_with_include_events_returns_the_events_of_each_article(
    repo: SqlArticleRepo,
) -> None:
    rows = _by_id(_search(repo, include=("events",)))
    events = rows["A"].events
    assert [e.event_id for e in events] == [2, 3, 1]  # num_mentions desc, id asc
    first = events[0]
    assert first.cameo_code == "040" and first.cameo_root == "04"
    assert first.goldstein == 1.5 and first.quad_class == 1
    assert first.num_mentions == 9 and first.num_sources == 2
    assert first.avg_tone == -2.5
    assert first.date == date(2026, 11, 2)
    assert first.source_url == "https://e.com/2"
    assert first.mention_count == 2  # mentions stored for event 2: A and X3
    assert events[2].mention_count == 3  # event 1: A, X1, X2
    assert events[2].actor1.model_dump() == {
        "code": "GOV", "name": "PRESIDENT", "country": "FR", "type": "GOV",
    }  # fmt: skip
    assert events[2].location is not None and events[2].location.lat == 48.85
    assert first.location is None and first.actor1.code is None  # event 2 has none


def test_list_new_and_summaries_return_the_same_events(repo: SqlArticleRepo) -> None:
    new = _by_id(repo.list_new(after_seq=0, since=None, limit=50, include=("events",)))
    assert [e.event_id for e in new["A"].events or []] == [2, 3, 1]
    by_id = repo.summaries(["A", "B"], include=("events",))
    assert [e.event_id for e in by_id["A"].events or []] == [2, 3, 1]
    assert by_id["B"].events == []


def test_semantic_summaries_delegate_with_the_same_cap(engine: Engine) -> None:
    semantic = SqlSemanticRepo(engine, events_per_article=3)
    got = semantic.summaries(["C"], include=("events",))
    assert [e.event_id for e in got["C"].events or []] == [124, 123, 122]


# TC-16: cap and order
def test_at_most_the_configured_number_of_events_in_order(
    repo: SqlArticleRepo, engine: Engine
) -> None:
    events = _by_id(_search(repo, include=("events",)))["C"].events
    assert len(events) == 20
    assert [e.event_id for e in events] == list(range(124, 104, -1))
    capped = SqlArticleRepo(engine, events_per_article=2)
    two = _by_id(_search(capped, include=("events",)))["C"].events
    assert [e.event_id for e in two] == [124, 123]


# TC-19: no events or only a mention of an unknown event is an empty list
def test_articles_without_events_get_an_empty_list(repo: SqlArticleRepo) -> None:
    rows = _by_id(_search(repo, include=("events",)))
    assert rows["B"].events == []
    assert rows["D"].events == []  # event 99 was never stored: hidden by the join


# TC-17 (repo half): not asked for means nothing is loaded and nothing is dumped
def test_without_include_events_stay_unset(repo: SqlArticleRepo) -> None:
    rows = _by_id(_search(repo))
    assert all(r.events is None for r in rows.values())
    assert all("events" not in r.to_json() for r in rows.values())
    tone_only = _by_id(_search(repo, include=("tone",)))
    assert all(r.events is None for r in tone_only.values())


def test_tone_and_events_together(repo: SqlArticleRepo) -> None:
    rows = _by_id(_search(repo, include=("tone", "events")))
    out = rows["A"].to_json(["tone", "events"])
    assert "tone" in out and len(out["events"]) == 3


# the detail always carries events
def test_get_always_carries_events(repo: SqlArticleRepo) -> None:
    detail = repo.get("A")
    assert detail is not None
    assert [e.event_id for e in detail.events] == [2, 3, 1]
    quiet = repo.get("B")
    assert quiet is not None and quiet.events == []


def test_events_become_visible_once_the_event_arrives(
    repo: SqlArticleRepo, engine: Engine
) -> None:
    assert _by_id(_search(repo, include=("events",)))["D"].events == []
    with Session(engine) as session:
        session.add(_event(99, num_mentions=4))
        session.commit()
    late = _by_id(_search(repo, include=("events",)))["D"].events
    assert [e.event_id for e in late] == [99]
