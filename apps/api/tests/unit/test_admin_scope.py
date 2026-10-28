"""TC-8 (AC-2, AC-3, AC-4, AC-5, AC-7): ownership on the admin routes, in memory.

The router is mounted alone behind a fake guard that picks the caller from a
header, over fakes that honour the scope like the SQL repos do. The router-walking
test fails when an agent or subscription route is added without joining the matrix.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from newsdock_api.adapters.admin import build_admin_router
from newsdock_api.adapters.agents_repo import DuplicateAgentError
from newsdock_api.domain.accounts import (
    AdminTokenPrincipal,
    Principal,
    Role,
    UserPrincipal,
)
from newsdock_api.domain.agents import (
    AgentScope,
    AgentSummary,
    GeneratedKey,
    KeySummary,
    RegisteredAgent,
)
from newsdock_api.domain.subscriptions import AdminSubscription

NOW = datetime(2026, 10, 28, tzinfo=UTC)
CALLERS: dict[str, Principal] = {
    "a": UserPrincipal(user_id="ua", email="a@x.io", role=Role.VIEWER),
    "b": UserPrincipal(user_id="ub", email="b@x.io", role=Role.ADMIN),
    "owner": UserPrincipal(user_id="uo", email="o@x.io", role=Role.OWNER),
    "token": AdminTokenPrincipal(),
}


def _visible(scope: AgentScope, owner_id: str | None) -> bool:
    if scope.everything:
        return True
    return scope.owner_id is not None and owner_id == scope.owner_id


class Registry:
    def __init__(self) -> None:
        # agent_id -> {name, owner_id, status, keys: {key_id: revoked}}
        self.agents: dict[str, dict[str, object]] = {}

    def _get(self, agent_id: str, scope: AgentScope) -> dict[str, object] | None:
        agent = self.agents.get(agent_id)
        if agent is None or not _visible(scope, agent["owner_id"]):  # type: ignore[arg-type]
            return None
        return agent

    def create_agent(
        self, name: str, key: GeneratedKey, owner_id: str | None
    ) -> RegisteredAgent:
        if any(a["name"] == name for a in self.agents.values()):
            raise DuplicateAgentError(name)
        agent_id = f"agent-{name}"
        self.agents[agent_id] = {
            "name": name,
            "owner_id": owner_id,
            "status": "active",
            "keys": {f"{agent_id}-k1": False},
        }
        return RegisteredAgent(id=agent_id, name=name, key_id=f"{agent_id}-k1")

    def agent_visible(self, agent_id: str, scope: AgentScope) -> bool:
        return self._get(agent_id, scope) is not None

    def add_key(
        self, agent_id: str, key: GeneratedKey, scope: AgentScope
    ) -> str | None:
        agent = self._get(agent_id, scope)
        if agent is None:
            return None
        keys: dict[str, bool] = agent["keys"]  # type: ignore[assignment]
        key_id = f"{agent_id}-k{len(keys) + 1}"
        keys[key_id] = False
        return key_id

    def revoke_key(self, agent_id: str, key_id: str, scope: AgentScope) -> bool:
        agent = self._get(agent_id, scope)
        keys: dict[str, bool] = agent["keys"] if agent else {}  # type: ignore[assignment]
        if key_id not in keys or keys[key_id]:
            return False
        keys[key_id] = True
        return True

    def set_status(self, agent_id: str, status: str, scope: AgentScope) -> bool:
        agent = self._get(agent_id, scope)
        if agent is None:
            return False
        agent["status"] = status
        return True

    def list_agents(self, scope: AgentScope) -> list[AgentSummary]:
        return [
            AgentSummary(
                agent_id=agent_id,
                name=str(a["name"]),
                status=str(a["status"]),
                keys=[
                    KeySummary(
                        key_id=kid,
                        prefix="p",
                        created_at=NOW,
                        revoked_at=NOW if revoked else None,
                        last_used_at=None,
                    )
                    for kid, revoked in a["keys"].items()  # type: ignore[attr-defined]
                ],
                owner_id=a["owner_id"],
                owner_email=None,
            )
            for agent_id, a in self.agents.items()
            if _visible(scope, a["owner_id"])  # type: ignore[arg-type]
        ]


class Subscriptions:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.rows: dict[str, str] = {}  # sub_id -> agent_id

    def add(self, sub_id: str, agent_id: str) -> None:
        self.rows[sub_id] = agent_id

    def list_visible(self, scope: AgentScope) -> list[AdminSubscription]:
        return [
            AdminSubscription(
                id=sub_id,
                agent_id=agent_id,
                filter={},
                created_at=NOW,
                agent_name=str(self.registry.agents[agent_id]["name"]),
            )
            for sub_id, agent_id in self.rows.items()
            if self.registry.agent_visible(agent_id, scope)
        ]

    def delete_visible(self, sub_id: str, scope: AgentScope) -> bool:
        agent_id = self.rows.get(sub_id)
        if agent_id is None or not self.registry.agent_visible(agent_id, scope):
            return False
        del self.rows[sub_id]
        return True

    # unused by the admin routes
    def create(self, *a: object, **k: object) -> object: ...
    def list_own(self, *a: object, **k: object) -> object: ...
    def get_own(self, *a: object, **k: object) -> object: ...
    def delete_own(self, *a: object, **k: object) -> object: ...
    def count_own(self, *a: object, **k: object) -> object: ...
    def exists(self, *a: object, **k: object) -> object: ...


def _guard(request: Request) -> Principal:
    who = CALLERS.get(request.headers.get("x-caller", ""))
    if who is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    return who


class Env:
    def __init__(self) -> None:
        self.registry = Registry()
        self.subs = Subscriptions(self.registry)
        router = build_admin_router(self.registry, self.subs, _guard)  # type: ignore[arg-type]
        self.router = router
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        # a1 belongs to user a, b1 to user b, o1 has no owner (created by the token)
        self.ids = {
            "a1": self.create("a", "a1"),
            "b1": self.create("b", "b1"),
            "o1": self.create("token", "o1"),
        }
        self.subs.add("sub-a1", self.ids["a1"])
        self.subs.add("sub-b1", self.ids["b1"])
        self.subs.add("sub-o1", self.ids["o1"])

    def call(self, who: str, method: str, path: str, **kw: object) -> int:
        return self.client.request(
            method,
            path,
            headers={"x-caller": who},
            **kw,  # type: ignore[arg-type]
        ).status_code

    def create(self, who: str, name: str) -> str:
        response = self.client.post(
            "/api/admin/agents", json={"name": name}, headers={"x-caller": who}
        )
        assert response.status_code == 201, response.text
        return str(response.json()["agent_id"])

    def listed(self, who: str) -> list[str]:
        response = self.client.get("/api/admin/agents", headers={"x-caller": who})
        assert response.status_code == 200
        return sorted(a["name"] for a in response.json())


@pytest.fixture()
def env() -> Env:
    return Env()


# --- AC-2: the creator is recorded ---
def test_a_session_creates_owned_agents_and_the_token_creates_ownerless_ones(
    env: Env,
) -> None:
    assert env.registry.agents[env.ids["a1"]]["owner_id"] == "ua"
    assert env.registry.agents[env.ids["b1"]]["owner_id"] == "ub"
    assert env.registry.agents[env.ids["o1"]]["owner_id"] is None


def test_the_owner_role_creates_agents_it_owns(env: Env) -> None:
    agent_id = env.create("owner", "mine")
    assert env.registry.agents[agent_id]["owner_id"] == "uo"


# --- AC-3, AC-5: listing ---
def test_listing_follows_the_callers_scope(env: Env) -> None:
    assert env.listed("a") == ["a1"]
    assert env.listed("b") == ["b1"]
    assert env.listed("owner") == ["a1", "b1", "o1"]
    assert env.listed("token") == ["a1", "b1", "o1"]


# --- AC-4, AC-5: acting on one agent ---
def _agent_actions(agent_id: str, key_id: str) -> list[tuple[str, str]]:
    base = f"/api/admin/agents/{agent_id}"
    return [
        ("POST", f"{base}/keys"),
        ("DELETE", f"{base}/keys/{key_id}"),
        ("POST", f"{base}/disable"),
        ("POST", f"{base}/enable"),
    ]


@pytest.mark.parametrize("target", ["a1", "o1"])
def test_the_wrong_user_gets_404_and_nothing_changes(env: Env, target: str) -> None:
    agent_id = env.ids[target]
    key_id = f"{agent_id}-k1"
    before = repr(env.registry.agents)
    # user b: a1 is another user's, o1 has no owner
    for method, path in _agent_actions(agent_id, key_id):
        assert env.call("b", method, path) == 404, (method, path)
    assert repr(env.registry.agents) == before


@pytest.mark.parametrize("who", ["a", "owner", "token"])
def test_the_owner_of_an_agent_the_owner_role_and_the_token_can_manage_it(
    env: Env, who: str
) -> None:
    agent_id = env.ids["a1"]
    key_id = f"{agent_id}-k1"
    assert env.call(who, "POST", f"/api/admin/agents/{agent_id}/keys") == 201
    assert env.call(who, "POST", f"/api/admin/agents/{agent_id}/disable") == 204
    assert env.call(who, "POST", f"/api/admin/agents/{agent_id}/enable") == 204
    assert env.call(who, "DELETE", f"/api/admin/agents/{agent_id}/keys/{key_id}") == 204


def test_only_the_owner_role_and_the_token_reach_ownerless_agents(env: Env) -> None:
    path = f"/api/admin/agents/{env.ids['o1']}/disable"
    assert env.call("a", "POST", path) == 404
    assert env.call("b", "POST", path) == 404
    assert env.call("owner", "POST", path) == 204
    assert env.call("token", "POST", path) == 204


def test_unknown_ids_look_the_same_as_foreign_ones(env: Env) -> None:
    for who in ("a", "owner"):
        assert env.call(who, "POST", "/api/admin/agents/nope/disable") == 404
        assert env.call(who, "POST", "/api/admin/agents/nope/keys") == 404
        assert env.call(who, "DELETE", "/api/admin/agents/nope/keys/k") == 404


def test_a_taken_name_is_409_for_everyone(env: Env) -> None:
    for who in ("a", "b", "owner", "token"):
        response = env.client.post(
            "/api/admin/agents", json={"name": "a1"}, headers={"x-caller": who}
        )
        assert response.status_code == 409


def test_no_credential_gets_401(env: Env) -> None:
    assert env.client.get("/api/admin/agents").status_code == 401


# --- AC-7: subscriptions follow the agent ---
def _sub_ids(env: Env, who: str) -> list[str]:
    response = env.client.get("/api/admin/subscriptions", headers={"x-caller": who})
    assert response.status_code == 200
    return sorted(s["id"] for s in response.json())


def test_subscription_listing_follows_the_scope(env: Env) -> None:
    assert _sub_ids(env, "a") == ["sub-a1"]
    assert _sub_ids(env, "b") == ["sub-b1"]
    assert _sub_ids(env, "owner") == ["sub-a1", "sub-b1", "sub-o1"]
    assert _sub_ids(env, "token") == ["sub-a1", "sub-b1", "sub-o1"]


def test_subscription_delete_follows_the_scope(env: Env) -> None:
    assert env.call("a", "DELETE", "/api/admin/subscriptions/sub-b1") == 404
    assert env.call("a", "DELETE", "/api/admin/subscriptions/sub-o1") == 404
    assert "sub-b1" in env.subs.rows
    assert env.call("a", "DELETE", "/api/admin/subscriptions/sub-a1") == 204
    assert env.call("owner", "DELETE", "/api/admin/subscriptions/sub-b1") == 204
    assert env.call("token", "DELETE", "/api/admin/subscriptions/sub-o1") == 204


# --- the router-walking meta-test ---
COVERED = {
    ("POST", "/api/admin/agents"),
    ("GET", "/api/admin/agents"),
    ("POST", "/api/admin/agents/{agent_id}/keys"),
    ("DELETE", "/api/admin/agents/{agent_id}/keys/{key_id}"),
    ("POST", "/api/admin/agents/{agent_id}/disable"),
    ("POST", "/api/admin/agents/{agent_id}/enable"),
    ("GET", "/api/admin/subscriptions"),
    ("DELETE", "/api/admin/subscriptions/{sub_id}"),
}


def test_every_agent_and_subscription_route_is_in_the_isolation_matrix(
    env: Env,
) -> None:
    routes = {
        (method, route.path)
        for route in env.router.routes
        if isinstance(route, APIRoute)
        and ("agents" in route.path or "subscriptions" in route.path)
        for method in (route.methods or set())
    }
    assert routes == COVERED, (
        "an /api/admin agent or subscription route is not covered by the "
        f"ownership tests: {routes ^ COVERED}"
    )
