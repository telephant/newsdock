"""TC-9 to TC-13 (AC-3, AC-5, AC-6, AC-8, AC-9, AC-10): agent ownership over HTTP.

A real Postgres (side port), the real app, one logged-in user per role and the
admin token. Callers are told apart by a cookie or an Authorization header.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PASSWORD = "correct-horse-battery"
TOKEN = "admin-token-for-tests"
NAMES = "/api/admin/agents"


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    mp = pytest.MonkeyPatch()
    mp.setenv("NEWSDOCK_ADMIN_TOKEN", TOKEN)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()
    mp.undo()


class World:
    """The app plus users: the first sign-up is the owner, `add` makes more."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.app = create_app(Settings(rate_limit_per_minute=0))
        self.client = TestClient(self.app)
        self.ids: dict[str, str] = {}
        self.auth: dict[str, dict[str, str]] = {
            "token": {"authorization": f"Bearer {TOKEN}"}
        }
        self.add("owner", "owner")
        self.add("a", "viewer")
        self.add("b", "admin")

    def add(self, name: str, role: str) -> None:
        email = f"{name}@x.io"
        body = {"email": email, "password": PASSWORD}
        self.client.post("/api/auth/signup", json=body)
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET role = :r WHERE email = :e"),
                {"r": role, "e": email},
            )
            self.ids[name] = str(
                conn.execute(
                    text("SELECT id FROM users WHERE email = :e"), {"e": email}
                ).scalar_one()
            )
        response = self.client.post("/api/auth/login", json=body)
        cookie = response.headers["set-cookie"].split(";")[0]
        self.auth[name] = {"cookie": cookie}

    def fresh(self) -> TestClient:
        return TestClient(self.app)  # no cookie jar: the header decides alone

    def req(self, who: str, method: str, path: str, **kw: Any) -> Any:
        return self.fresh().request(method, path, headers=self.auth[who], **kw)

    def create(self, who: str, name: str) -> dict[str, Any]:
        response = self.req(who, "POST", NAMES, json={"name": name})
        assert response.status_code == 201, response.text
        return dict(response.json())

    def names(self, who: str) -> list[str]:
        response = self.req(who, "GET", NAMES)
        assert response.status_code == 200, response.text
        return sorted(a["name"] for a in response.json())


@pytest.fixture()
def world(engine: Engine) -> Callable[[], World]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        conn.execute(text("TRUNCATE agents CASCADE"))
    return lambda: World(engine)


def _bearer(key: str) -> dict[str, str]:
    return {"authorization": f"Bearer {key}"}


# TC-9: a plain signed-up user manages their own agents end to end (AC-9)
def test_a_viewer_runs_the_whole_agent_lifecycle(world: Callable[[], World]) -> None:
    w = world()
    issued = w.create("a", "alpha")
    agent_id, key = issued["agent_id"], issued["api_key"]
    assert w.names("a") == ["alpha"]

    new_key = w.req("a", "POST", f"{NAMES}/{agent_id}/keys")
    assert new_key.status_code == 201
    revoke = w.req("a", "DELETE", f"{NAMES}/{agent_id}/keys/{new_key.json()['key_id']}")
    assert revoke.status_code == 204

    # the agent saves a subscription with its key; its owner lists and deletes it
    created = w.fresh().post("/api/subscriptions", headers=_bearer(key), json={})
    assert created.status_code == 201, created.text
    listed = w.req("a", "GET", "/api/admin/subscriptions")
    assert [s["agent_name"] for s in listed.json()] == ["alpha"]
    sub_id = created.json()["id"]
    assert w.req("a", "DELETE", f"/api/admin/subscriptions/{sub_id}").status_code == 204

    assert w.req("a", "POST", f"{NAMES}/{agent_id}/disable").status_code == 204


def test_anonymous_gets_401_and_an_agent_key_gets_403(
    world: Callable[[], World],
) -> None:
    w = world()
    key = w.create("a", "alpha")["api_key"]
    anon = w.fresh()
    assert anon.get(NAMES).status_code == 401
    assert anon.get("/api/admin/subscriptions").status_code == 401
    assert anon.get(NAMES, headers=_bearer(key)).status_code == 403


# TC-10: who sees which agents (AC-3, AC-5)
def test_listing_and_ownerless_agents_across_the_roles(
    world: Callable[[], World],
) -> None:
    w = world()
    w.create("a", "a1")
    w.create("b", "b1")
    w.create("token", "o1")  # the admin token makes an agent with no owner

    assert w.names("a") == ["a1"]
    assert w.names("b") == ["b1"]
    assert w.names("owner") == ["a1", "b1", "o1"]
    assert w.names("token") == ["a1", "b1", "o1"]

    by_name = {a["name"]: a for a in w.req("owner", "GET", NAMES).json()}
    assert by_name["a1"]["owner_email"] == "a@x.io"
    assert by_name["o1"]["owner_id"] is None and by_name["o1"]["owner_email"] is None

    o1 = by_name["o1"]["agent_id"]
    for who in ("a", "b"):
        assert w.req(who, "POST", f"{NAMES}/{o1}/disable").status_code == 404
    assert w.req("owner", "POST", f"{NAMES}/{o1}/disable").status_code == 204
    assert w.req("owner", "POST", f"{NAMES}/{o1}/enable").status_code == 204


def test_a_user_cannot_touch_another_users_agent_or_subscription(
    world: Callable[[], World],
) -> None:
    w = world()
    issued = w.create("a", "a1")
    agent_id = issued["agent_id"]
    sub = (
        w.fresh()
        .post("/api/subscriptions", headers=_bearer(issued["api_key"]), json={})
        .json()
    )
    for method, path in (
        ("POST", f"{NAMES}/{agent_id}/keys"),
        ("POST", f"{NAMES}/{agent_id}/disable"),
        ("POST", f"{NAMES}/{agent_id}/enable"),
        ("DELETE", f"{NAMES}/{agent_id}/keys/{issued['key_id']}"),
        ("DELETE", f"/api/admin/subscriptions/{sub['id']}"),
    ):
        assert w.req("b", method, path).status_code == 404, (method, path)
    assert w.req("b", "GET", "/api/admin/subscriptions").json() == []
    # nothing changed: the key still works and the subscription is still there
    assert (
        w.fresh().get("/api/subscriptions", headers=_bearer(issued["api_key"])).json()
    )


# TC-11: deleting the owner's account orphans the agent; the key keeps working (AC-8)
def test_deleting_a_user_orphans_their_agents(world: Callable[[], World]) -> None:
    w = world()
    issued = w.create("a", "a1")
    w.create("b", "b1")

    assert w.req("owner", "DELETE", f"/api/users/{w.ids['a']}").status_code == 204

    still = w.fresh().get("/api/subscriptions", headers=_bearer(issued["api_key"]))
    assert still.status_code == 200
    assert w.names("b") == ["b1"]  # the orphan is in nobody's own list
    listed = {a["name"]: a for a in w.req("owner", "GET", NAMES).json()}
    assert listed["a1"]["owner_id"] is None and listed["a1"]["owner_email"] is None


# TC-12: agent-facing paths do not care who owns the agent (AC-6)
def test_owned_and_ownerless_agent_keys_work_on_the_agent_paths(
    world: Callable[[], World],
) -> None:
    w = world()
    owned = w.create("a", "a1")["api_key"]
    ownerless = w.create("token", "o1")["api_key"]
    with TestClient(w.app) as client:
        for key in (owned, ownerless):
            headers = _bearer(key)
            mcp = client.post(
                "/mcp",
                headers={
                    **headers,
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json={},
            )
            assert mcp.status_code not in (401, 403), mcp.text
            made = client.post("/api/subscriptions", headers=headers, json={})
            assert made.status_code == 201
            assert len(client.get("/api/subscriptions", headers=headers).json()) == 1
            assert (
                client.delete(
                    f"/api/subscriptions/{made.json()['id']}", headers=headers
                ).status_code
                == 204
            )


# TC-13: user management is unchanged: owner only (AC-10)
def test_only_the_owner_role_manages_users(world: Callable[[], World]) -> None:
    w = world()
    key = w.create("a", "a1")["api_key"]
    expected = {"owner": 200, "b": 403, "a": 403}
    for who, status in expected.items():
        assert w.req(who, "GET", "/api/users").status_code == status, who
    assert w.fresh().get("/api/users", headers=_bearer(key)).status_code == 403
    assert w.fresh().get("/api/users").status_code == 401


# TC-14 (API half): `make agent-create` is this request; the agent has no owner (AC-10)
def test_the_cli_request_creates_an_ownerless_agent_the_owner_can_manage(
    world: Callable[[], World], engine: Engine
) -> None:
    w = world()
    response = w.fresh().post(
        NAMES,
        headers={**_bearer(TOKEN), "Content-Type": "application/json"},
        json={"name": "demo-financial"},
    )
    assert response.status_code == 201
    assert response.json()["api_key"].startswith("ndk_")
    with engine.connect() as conn:
        owner = conn.execute(
            text("SELECT owner_id FROM agents WHERE name = 'demo-financial'")
        ).scalar_one()
    assert owner is None
    assert w.names("a") == []  # not in an ordinary user's list
    assert w.names("owner") == ["demo-financial"]  # the owner role can manage it
