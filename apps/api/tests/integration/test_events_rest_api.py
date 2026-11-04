"""TC-17, TC-18, TC-19, TC-20 (REST halves): `include=events` on `GET /api/articles`
and the always-on `events` of the detail route (Docker, side Postgres, in-process
client)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from newsdock_db.models import Event, Mention
from newsdock_db.testing import article
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
ADDED = datetime(2026, 11, 2, 11, tzinfo=UTC)

# The keys of an article in a default feed response before this feature.
GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count",
}  # fmt: skip
EVENT_KEYS = {
    "event_id", "date", "cameo_code", "cameo_root", "goldstein", "quad_class",
    "num_mentions", "num_sources", "avg_tone", "actor1", "actor2", "location",
    "source_url", "mention_count",
}  # fmt: skip


def _event(event_id: int, num_mentions: int) -> Event:
    return Event(
        event_id=event_id, event_date=date(2026, 11, 2), is_root=False,
        cameo_code="040", cameo_base="040", cameo_root="04", quad_class=1,
        goldstein=1.5, num_mentions=num_mentions, num_sources=2, num_articles=3,
        avg_tone=-2.5, actor1_code="GOV", actor1_name="PRESIDENT",
        geo_name="Paris, France", geo_country="FR", geo_lat=48.85, geo_lon=2.35,
        date_added=ADDED, source_url=f"https://e.com/{event_id}",
        source_url_hash="A",
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
        session.add_all(
            [
                article("A", "Protest in Paris", model=None, tone=-4.0, tone_neg=9.5),
                article("B", "Quiet day", model=None, tone=1.0, tone_neg=2.0),
            ]
        )
        session.commit()
        session.add_all([_event(1, 5), _event(2, 9), _event(3, 1)])
        session.add_all(
            [
                _mention(1, "A"),
                _mention(2, "A"),
                _mention(1, "X1"),
                _mention(2, "X2"),
                # event 3 is mentioned by a copy of A only: the sink's derived row
                _mention(3, "X3"),
                _mention(3, "A", derived=True),
            ]
        )
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def agent(engine: Engine) -> tuple[str, str]:
    made = make_key()
    registered = SqlAgentsRepo(engine).create_agent("events-rest", made, None)
    return registered.id, made.raw


@pytest.fixture(scope="module")
def client(engine: Engine) -> TestClient:
    return TestClient(create_app(Settings(auth_required=True, rate_limit_per_minute=0)))


def headers(agent: tuple[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {agent[1]}"}


def feed(client: TestClient, agent: tuple[str, str], **params: Any) -> dict[str, Any]:
    response = client.get("/api/articles", params=params, headers=headers(agent))
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def by_id(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["article_id"]: a for a in body["articles"]}


# --- TC-17 (AC-10): nothing changes without include=events ---------------------------
def test_default_feed_has_exactly_the_golden_keys(
    client: TestClient, agent: tuple[str, str]
) -> None:
    body = feed(client, agent)
    assert set(by_id(body)) == {"A", "B"}
    assert all(set(a) == GOLDEN for a in body["articles"])
    tone_only = feed(client, agent, include="tone_neg")
    assert all(set(a) == GOLDEN | {"tone_neg"} for a in tone_only["articles"])


# --- TC-18 (AC-11): the list with include=events -------------------------------------
def test_feed_include_events_adds_the_events_key(
    client: TestClient, agent: tuple[str, str]
) -> None:
    rows = by_id(feed(client, agent, include="events"))
    assert set(rows["A"]) == GOLDEN | {"events"}
    events = rows["A"]["events"]
    assert [e["event_id"] for e in events] == [2, 1, 3]  # most mentioned first
    assert set(events[0]) == EVENT_KEYS
    assert events[0]["mention_count"] == 2 and events[0]["num_mentions"] == 9
    assert events[0]["date"] == "2026-11-02"
    assert events[0]["location"]["name"] == "Paris, France"


def test_events_and_tone_can_be_asked_together(
    client: TestClient, agent: tuple[str, str]
) -> None:
    rows = by_id(feed(client, agent, include="tone_neg,events"))
    assert set(rows["A"]) == GOLDEN | {"tone_neg", "events"}
    assert rows["A"]["tone_neg"] == 9.5


# --- TC-19 (AC-12): none stored is an empty list -------------------------------------
def test_an_article_without_events_gets_an_empty_list(
    client: TestClient, agent: tuple[str, str]
) -> None:
    rows = by_id(feed(client, agent, include="events"))
    assert rows["B"]["events"] == []


# --- TC-18 (AC-11): the detail always carries events ---------------------------------
def test_detail_always_carries_events(
    client: TestClient, agent: tuple[str, str]
) -> None:
    detail = client.get("/api/articles/A", headers=headers(agent))
    assert detail.status_code == 200
    assert [e["event_id"] for e in detail.json()["events"]] == [2, 1, 3]
    quiet = client.get("/api/articles/B", headers=headers(agent))
    assert quiet.json()["events"] == []


# --- TC-20 (AC-13): unknown names are 422 invalid_include ----------------------------
@pytest.mark.parametrize("value", ["bogus", "events,bogus", "Events"])
def test_unknown_include_is_a_422(
    client: TestClient, agent: tuple[str, str], value: str
) -> None:
    response = client.get(
        "/api/articles", params={"include": value}, headers=headers(agent)
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_include"


# --- TC-11 (AC-9), TC-4: an event reached through a copy shows on the canonical ------
def test_event_of_a_copy_shows_on_the_canonical_with_real_mention_count(
    client: TestClient, agent: tuple[str, str]
) -> None:
    feed_events = by_id(feed(client, agent, include="events"))["A"]["events"]
    detail_events = client.get("/api/articles/A", headers=headers(agent)).json()[
        "events"
    ]
    for events in (feed_events, detail_events):
        third = next(e for e in events if e["event_id"] == 3)
        assert third["mention_count"] == 1  # the copy's own mention, not the link
