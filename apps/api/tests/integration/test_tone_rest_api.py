"""TC-3, TC-8, TC-9, TC-10, TC-11, TC-14, TC-18 (REST halves): `include` and
`min_negativity` on `GET /api/articles`, the detail route, and the subscription route
(Docker, side Postgres, in-process client)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.http import create_app
from newsdock_api.adapters.subscriptions_repo import SqlSubscriptionsRepo
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from newsdock_db.testing import article
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]

GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count",
}  # fmt: skip
STORED = {"A": 9.5, "B": 3.0, "C": 12.5, "D": 8.0, "E": None, "F": 9.7}


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(eng) as session:
        session.add_all(
            [
                article("A", "Central bank raises interest rates", model=None,
                        themes=["ECON_RATES"], tone=-4.0, tone_pos=1.5,
                        tone_neg=9.5, tone_polarity=11.0),
                article("B", "Wildfire spreads across the hills", model=None,
                        tone=2.0, tone_neg=3.0),
                article("C", "Interest rates tumble sharply", model=None,
                        tone=-12.0, tone_neg=12.5),
                article("D", "Opposition wins the vote", model=None,
                        tone=-8.0, tone_neg=8.0),
                article("E", "Interest rates explained for beginners", model=None),
                article("F", "Rates outlook darkens", model=None,
                        tone=-9.7, tone_neg=9.7),
            ]
        )  # fmt: skip
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def agent(engine: Engine) -> tuple[str, str]:
    made = make_key()
    registered = SqlAgentsRepo(engine).create_agent("tone-rest", made, None)
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


def ids(body: dict[str, Any]) -> set[str]:
    return {a["article_id"] for a in body["articles"]}


# --- TC-3 (AC-1) --------------------------------------------------------------------
def test_default_feed_has_exactly_the_golden_keys(
    client: TestClient, agent: tuple[str, str]
) -> None:
    body = feed(client, agent)
    assert set(body) == {"articles", "next_before"}
    assert ids(body) == set("ABCDEF")
    assert all(set(a) == GOLDEN for a in body["articles"])
    assert isinstance(body["next_before"], str)


# --- TC-8 (AC-5) --------------------------------------------------------------------
def test_include_adds_only_the_requested_keys(
    client: TestClient, agent: tuple[str, str]
) -> None:
    body = feed(client, agent, include="tone,tone_neg")
    by_id = {a["article_id"]: a for a in body["articles"]}
    assert set(by_id) == set("ABCDEF")
    for name, stored in STORED.items():
        assert set(by_id[name]) == GOLDEN | {"tone", "tone_neg"}
        assert by_id[name]["tone_neg"] == stored
    assert (by_id["A"]["tone"], by_id["C"]["tone"]) == (-4.0, -12.0)


def test_include_does_not_change_paging(
    client: TestClient, agent: tuple[str, str]
) -> None:
    plain = feed(client, agent, limit=2)
    asked = feed(client, agent, limit=2, include="tone")
    assert [a["article_id"] for a in plain["articles"]] == [
        a["article_id"] for a in asked["articles"]
    ]
    assert plain["next_before"] == asked["next_before"]


def test_repeated_and_blank_include_pieces_are_tolerated(
    client: TestClient, agent: tuple[str, str]
) -> None:
    body = feed(client, agent, include="tone_neg,,tone_neg")
    assert all(set(a) == GOLDEN | {"tone_neg"} for a in body["articles"])
    assert all(set(a) == GOLDEN for a in feed(client, agent, include="")["articles"])


# --- TC-9 (AC-6) --------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["tone_x", "Tone", "tone,word_count", "title"])
def test_unknown_include_is_422_invalid_include(
    client: TestClient, agent: tuple[str, str], bad: str
) -> None:
    response = client.get(
        "/api/articles", params={"include": bad}, headers=headers(agent)
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_include"


# --- TC-10 (AC-7) -------------------------------------------------------------------
def test_a_row_without_tone_is_null_when_asked_and_absent_otherwise(
    client: TestClient, agent: tuple[str, str]
) -> None:
    (row,) = feed(client, agent, text="explained", include="tone,tone_neg")["articles"]
    assert row["article_id"] == "E"
    assert row["tone"] is None and row["tone_neg"] is None
    (plain,) = feed(client, agent, text="explained")["articles"]
    assert set(plain) == GOLDEN


# --- TC-11 (AC-8) -------------------------------------------------------------------
def test_detail_returns_all_four_tone_numbers(
    client: TestClient, agent: tuple[str, str]
) -> None:
    response = client.get("/api/articles/A", headers=headers(agent))
    assert response.status_code == 200
    body = response.json()
    assert (
        body["tone"],
        body["tone_pos"],
        body["tone_neg"],
        body["tone_polarity"],
    ) == (
        -4.0,
        1.5,
        9.5,
        11.0,
    )
    empty = client.get("/api/articles/E", headers=headers(agent)).json()
    assert empty["tone"] is None and empty["tone_neg"] is None
    assert empty["tone_pos"] is None and empty["tone_polarity"] is None


# --- TC-14 (AC-11) and the AND rule (AC-14) -----------------------------------------
def test_min_negativity_filters_the_feed(
    client: TestClient, agent: tuple[str, str]
) -> None:
    assert ids(feed(client, agent, min_negativity=8)) == set("ACDF")
    assert ids(feed(client, agent, min_negativity=9.7)) == set("CF")
    assert ids(feed(client, agent, min_negativity=0)) == set("ABCDF")
    assert ids(feed(client, agent, min_negativity=100)) == set()
    assert ids(feed(client, agent, min_negativity=8, theme="ECON_*")) == {"A"}
    assert ids(feed(client, agent, min_negativity=8, text="rates")) == set("ACF")
    assert ids(feed(client, agent, min_negativity=8, domain="nowhere.org")) == set()


def test_the_filter_and_include_work_together(
    client: TestClient, agent: tuple[str, str]
) -> None:
    body = feed(client, agent, min_negativity=9.7, include="tone_neg")
    assert {a["article_id"]: a["tone_neg"] for a in body["articles"]} == {
        "C": 12.5,
        "F": 9.7,
    }


# --- TC-18 (AC-13) ------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["-1", "101", "100.5", "abc", "true", "", "nan", "inf"])
def test_bad_min_negativity_is_422(
    client: TestClient, agent: tuple[str, str], bad: str
) -> None:
    response = client.get(
        "/api/articles", params={"min_negativity": bad}, headers=headers(agent)
    )
    assert response.status_code == 422


def test_out_of_range_names_the_error(
    client: TestClient, agent: tuple[str, str]
) -> None:
    response = client.get(
        "/api/articles", params={"min_negativity": "101"}, headers=headers(agent)
    )
    assert response.json()["detail"] == "invalid_filter"


def test_subscription_with_a_number_is_stored_and_bad_ones_are_not(
    client: TestClient, agent: tuple[str, str], engine: Engine
) -> None:
    ok = client.post(
        "/api/subscriptions", json={"min_negativity": 8}, headers=headers(agent)
    )
    assert ok.status_code == 201
    assert ok.json()["filter"] == {"min_negativity": 8}
    repo = SqlSubscriptionsRepo(engine)
    before = len(repo.list_own(agent[0]))
    for bad in (101, -1, True, "8"):
        response = client.post(
            "/api/subscriptions", json={"min_negativity": bad}, headers=headers(agent)
        )
        assert response.status_code == 422, bad
    assert len(repo.list_own(agent[0])) == before
