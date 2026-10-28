"""TC-24, TC-26, TC-30, TC-35: roles, users routes, admin by session (Docker)."""

import subprocess
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

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
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-login-test"
PASSWORD = "correct-horse-battery"
ADMIN = "admin-token-for-tests"
NO_SUCH_UUID = "00000000-0000-0000-0000-000000000000"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert _compose("up", "-d", "--wait", "postgres").returncode == 0
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in (ROOT / ".env.example").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{env.get('POSTGRES_PORT', '5433')}/{env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    mp.setenv("NEWSDOCK_ADMIN_TOKEN", ADMIN)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(url)
    yield eng
    eng.dispose()
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


class World:
    """An app, a database and one logged-in user per role (cookies as headers)."""

    def __init__(self, engine: Engine, **settings: object) -> None:
        self.engine = engine
        self.app = create_app(Settings(**settings))  # type: ignore[arg-type]
        self.client = TestClient(self.app)
        self.ids: dict[str, str] = {}
        self.cookie: dict[str, dict[str, str]] = {}
        for role in ("owner", "admin", "viewer"):  # the first sign-up is the owner
            self.add(role, role)

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
        token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        self.cookie[name] = {"cookie": f"newsdock_session={token}"}

    def fresh(self) -> TestClient:
        return TestClient(self.app)  # no cookie jar


@pytest.fixture()
def world(engine: Engine) -> Callable[..., World]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        conn.execute(text("TRUNCATE agents CASCADE"))

    def build(**settings: object) -> World:
        return World(engine, **settings)

    return build


# ---- TC-24 ------------------------------------------------------------------------
def test_role_matrix_on_agent_and_user_management(
    world: Callable[..., World], engine: Engine
) -> None:
    w = world()
    expected = {
        "viewer": (403, 403),
        "admin": (200, 403),
        "owner": (200, 200),
    }
    for role, (agents, users) in expected.items():
        c = w.fresh()
        assert c.get("/api/admin/agents", headers=w.cookie[role]).status_code == agents
        assert c.get("/api/users", headers=w.cookie[role]).status_code == users


@pytest.mark.parametrize("auth_required", [True, False])
def test_agent_keys_and_anonymous_callers_on_management_routes(
    world: Callable[..., World], engine: Engine, auth_required: bool
) -> None:
    w = world(auth_required=auth_required)
    key = make_key()
    SqlAgentsRepo(engine).create_agent("alpha", key, None)
    c = w.fresh()
    bearer = {"authorization": f"Bearer {key.raw}"}
    for path in ("/api/admin/agents", "/api/users"):
        assert c.get(path, headers=bearer).status_code == 403, path
        assert c.get(path).status_code == 401, path  # management is never open


def test_a_role_change_applies_to_the_open_session_at_once(
    world: Callable[..., World],
) -> None:
    w = world()
    c = w.fresh()
    assert c.get("/api/admin/agents", headers=w.cookie["viewer"]).status_code == 403
    assert (
        c.patch(
            f"/api/users/{w.ids['viewer']}",
            json={"role": "admin"},
            headers=w.cookie["owner"],
        ).status_code
        == 200
    )
    assert c.get("/api/admin/agents", headers=w.cookie["viewer"]).status_code == 200


def test_the_users_list_never_carries_a_hash(world: Callable[..., World]) -> None:
    w = world()
    rows = w.fresh().get("/api/users", headers=w.cookie["owner"]).json()
    assert {r["email"] for r in rows} == {"owner@x.io", "admin@x.io", "viewer@x.io"}
    assert all(set(r) == {"id", "email", "role", "created_at"} for r in rows)


# ---- TC-26 ------------------------------------------------------------------------
def test_promote_demote_and_the_last_owner_rule(world: Callable[..., World]) -> None:
    w = world()
    c, owner = w.fresh(), w.cookie["owner"]
    ok = c.patch(f"/api/users/{w.ids['viewer']}", json={"role": "admin"}, headers=owner)
    assert ok.status_code == 200 and ok.json()["role"] == "admin"
    me = w.ids["owner"]
    demote = c.patch(f"/api/users/{me}", json={"role": "viewer"}, headers=owner)
    assert (demote.status_code, demote.json()["detail"]) == (409, "last_owner")
    gone = c.delete(f"/api/users/{me}", headers=owner)
    assert (gone.status_code, gone.json()["detail"]) == (409, "last_owner")
    assert c.get("/api/auth/me", headers=owner).json()["role"] == "owner"


def test_user_route_errors(world: Callable[..., World]) -> None:
    w = world()
    c, owner = w.fresh(), w.cookie["owner"]
    path = f"/api/users/{w.ids['viewer']}"
    assert c.patch(path, json={"role": "root"}, headers=owner).status_code == 422
    assert c.patch(path, json={}, headers=owner).status_code == 422
    for bad in (NO_SUCH_UUID, "not-a-uuid"):
        assert (
            c.patch(
                f"/api/users/{bad}", json={"role": "admin"}, headers=owner
            ).status_code
            == 404
        )
        assert c.delete(f"/api/users/{bad}", headers=owner).status_code == 404
    for role in ("viewer", "admin"):
        headers = w.cookie[role]
        assert c.patch(path, json={"role": "admin"}, headers=headers).status_code == 403
        assert c.delete(path, headers=headers).status_code == 403


def test_deleting_a_user_ends_their_sessions(world: Callable[..., World]) -> None:
    w = world()
    c = w.fresh()
    assert c.get("/api/auth/me", headers=w.cookie["viewer"]).status_code == 200
    gone = c.delete(f"/api/users/{w.ids['viewer']}", headers=w.cookie["owner"])
    assert gone.status_code == 204
    assert c.get("/api/auth/me", headers=w.cookie["viewer"]).status_code == 401
    emails = [u["email"] for u in c.get("/api/users", headers=w.cookie["owner"]).json()]
    assert "viewer@x.io" not in emails


def test_two_owners_demoting_each_other_over_http_keep_one_owner(
    world: Callable[..., World], engine: Engine
) -> None:
    for _ in range(5):
        w = world()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET role = 'owner' WHERE email = 'admin@x.io'")
            )
        statuses: list[int] = []
        barrier = threading.Barrier(2)

        def demote(victim: str, actor: str) -> None:
            client = w.fresh()
            barrier.wait()
            response = client.patch(
                f"/api/users/{w.ids[victim]}", json={"role": "viewer"},
                headers=w.cookie[actor],
            )  # fmt: skip
            statuses.append(response.status_code)

        threads = [
            threading.Thread(target=demote, args=("owner", "admin")),
            threading.Thread(target=demote, args=("admin", "owner")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with engine.connect() as conn:
            owners = conn.execute(
                text("SELECT count(*) FROM users WHERE role = 'owner'")
            ).scalar_one()
        # one demotion wins; the other is refused as 403 (its actor was just
        # demoted) or 409 (both passed the role check, the lock refuses the last)
        assert owners == 1, (statuses, owners)
        assert sorted(statuses) in ([200, 403], [200, 409]), statuses
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE users CASCADE"))


# ---- TC-30 ------------------------------------------------------------------------
def test_admin_lists_and_deletes_subscriptions(
    world: Callable[..., World], engine: Engine
) -> None:
    w = world()
    agents, subs = SqlAgentsRepo(engine), SqlSubscriptionsRepo(engine)
    alpha_key, beta_key = make_key(), make_key()
    alpha = agents.create_agent("alpha", alpha_key, None)
    beta = agents.create_agent("beta", beta_key, None)
    keep = subs.create(beta.id, {"domain": "other.org"})
    drop = subs.create(alpha.id, {"theme": "ECON_*"})
    c = w.fresh()
    admin = w.cookie["admin"]

    listed = c.get("/api/admin/subscriptions", headers=admin).json()
    assert {(r["agent_name"], r["id"]) for r in listed} == {
        ("alpha", drop.id),
        ("beta", keep.id),
    }
    assert (
        c.delete(
            f"/api/admin/subscriptions/{drop.id}", headers=w.cookie["viewer"]
        ).status_code
        == 403
    )
    assert (
        c.delete(f"/api/admin/subscriptions/{NO_SUCH_UUID}", headers=admin).status_code
        == 404
    )
    assert (
        c.delete("/api/admin/subscriptions/not-a-uuid", headers=admin).status_code
        == 404
    )

    assert (
        c.delete(f"/api/admin/subscriptions/{drop.id}", headers=admin).status_code
        == 204
    )
    after = c.get("/api/admin/subscriptions", headers=admin).json()
    assert [r["id"] for r in after] == [keep.id]
    assert not subs.exists(drop.id) and subs.exists(keep.id)
    # the owning agent's stream for it is gone at once (open ones end at the next ping)
    stream = c.get(
        f"/api/subscriptions/{drop.id}/stream",
        headers={"authorization": f"Bearer {alpha_key.raw}"},
    )
    assert stream.status_code == 404


def test_the_admin_token_can_delete_a_subscription_too(
    world: Callable[..., World], engine: Engine
) -> None:
    w = world()
    agent = SqlAgentsRepo(engine).create_agent("alpha", make_key(), None)
    sub = SqlSubscriptionsRepo(engine).create(agent.id, {})
    response = w.fresh().delete(
        f"/api/admin/subscriptions/{sub.id}",
        headers={"authorization": f"Bearer {ADMIN}"},
    )
    assert response.status_code == 204


# ---- TC-35 ------------------------------------------------------------------------
def test_admin_token_matrix(world: Callable[..., World], engine: Engine) -> None:
    w = world()
    key = make_key()
    SqlAgentsRepo(engine).create_agent("alpha", key, None)
    c = w.fresh()
    token = {"authorization": f"Bearer {ADMIN}"}
    assert c.get("/api/admin/agents", headers=token).status_code == 200
    wrong = {"authorization": "Bearer not-the-token"}
    assert c.get("/api/admin/agents", headers=wrong).status_code == 401
    agent = {"authorization": f"Bearer {key.raw}"}
    assert c.get("/api/admin/agents", headers=agent).status_code == 403
    # the token is not a user: it opens neither the users routes nor logout
    assert c.get("/api/users", headers=token).status_code == 401
    assert c.post("/api/auth/logout", headers=token).status_code == 401
    # a token request that also carries a viewer cookie is the token's, not the viewer's
    both = {**token, **w.cookie["viewer"]}
    assert c.get("/api/admin/agents", headers=both).status_code == 200


def test_without_a_configured_token_sessions_still_manage_agents(
    world: Callable[..., World], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEWSDOCK_ADMIN_TOKEN")
    w = world()
    c = w.fresh()
    assert c.get("/api/admin/agents", headers=w.cookie["admin"]).status_code == 200
    token = {"authorization": f"Bearer {ADMIN}"}
    assert c.get("/api/admin/agents", headers=token).status_code == 401
    assert c.get("/api/admin/agents").status_code == 401
