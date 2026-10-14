"""TC-1, TC-8 (AC-1, AC-7): admin routes over an in-memory registry."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from newsdock_api.adapters.agents_repo import DuplicateAgentError
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.agents import (
    AgentSummary,
    GeneratedKey,
    KeySummary,
    RegisteredAgent,
    make_key,
)

TOKEN = "admin-token-for-tests"
NOW = datetime(2026, 10, 14, tzinfo=UTC)


class FakeRegistry:
    """Same surface as SqlAgentsRepo for the admin routes."""

    def __init__(self) -> None:
        self.agents: dict[str, dict[str, object]] = {}

    def create_agent(self, name: str, key: GeneratedKey) -> RegisteredAgent:
        if any(a["name"] == name for a in self.agents.values()):
            raise DuplicateAgentError(name)
        agent_id = f"a{len(self.agents) + 1}"
        key_id = f"{agent_id}-k1"
        self.agents[agent_id] = {
            "name": name,
            "status": "active",
            "keys": {key_id: [key.prefix, False]},
        }
        return RegisteredAgent(id=agent_id, name=name, key_id=key_id)

    def add_key(self, agent_id: str, key: GeneratedKey) -> str:
        keys: dict[str, list[object]] = self.agents[agent_id]["keys"]  # type: ignore[assignment]
        key_id = f"{agent_id}-k{len(keys) + 1}"
        keys[key_id] = [key.prefix, False]
        return key_id

    def revoke_key(self, agent_id: str, key_id: str) -> bool:
        agent = self.agents.get(agent_id)
        keys: dict[str, list[object]] = agent["keys"] if agent else {}  # type: ignore[assignment]
        if key_id not in keys or keys[key_id][1]:
            return False
        keys[key_id][1] = True
        return True

    def set_status(self, agent_id: str, status: str) -> bool:
        if agent_id not in self.agents:
            return False
        self.agents[agent_id]["status"] = status
        return True

    def list_agents(self) -> list[AgentSummary]:
        return [
            AgentSummary(
                agent_id=agent_id,
                name=str(a["name"]),
                status=str(a["status"]),
                keys=[
                    KeySummary(
                        key_id=key_id,
                        prefix=str(prefix),
                        created_at=NOW,
                        revoked_at=NOW if revoked else None,
                        last_used_at=None,
                    )
                    for key_id, (prefix, revoked) in a["keys"].items()  # type: ignore[attr-defined]
                ],
            )
            for agent_id, a in self.agents.items()
        ]


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost:5/x")
    monkeypatch.delenv("NEWSDOCK_ADMIN_TOKEN", raising=False)


def client(registry: FakeRegistry, token: str | None = TOKEN) -> TestClient:
    return TestClient(create_app(Settings(admin_token=token), agents_repo=registry))


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# TC-1
def test_create_returns_the_key_once_and_listing_hides_it() -> None:
    registry = FakeRegistry()
    c = client(registry)
    response = c.post("/api/admin/agents", json={"name": "alpha"}, headers=auth())
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"agent_id", "name", "key_id", "api_key"}
    assert body["api_key"].startswith("ndk_")

    listing = c.get("/api/admin/agents", headers=auth())
    assert listing.status_code == 200
    (agent,) = listing.json()
    assert agent["name"] == "alpha" and agent["keys"][0]["prefix"] in body["api_key"]
    secret = body["api_key"].split("_")[2]
    assert secret not in listing.text and "key_hash" not in listing.text


def test_duplicate_name_is_409_and_bad_names_are_422() -> None:
    c = client(FakeRegistry())
    assert (
        c.post("/api/admin/agents", json={"name": "alpha"}, headers=auth()).status_code
        == 201
    )
    assert (
        c.post("/api/admin/agents", json={"name": "alpha"}, headers=auth()).status_code
        == 409
    )
    for bad in ("", "Has Space", "UPPER", "x" * 41):
        assert (
            c.post("/api/admin/agents", json={"name": bad}, headers=auth()).status_code
            == 422
        )


def test_key_lifecycle_routes() -> None:
    registry = FakeRegistry()
    c = client(registry)
    agent = c.post("/api/admin/agents", json={"name": "alpha"}, headers=auth()).json()
    aid = agent["agent_id"]

    extra = c.post(f"/api/admin/agents/{aid}/keys", headers=auth())
    assert extra.status_code == 201 and extra.json()["api_key"].startswith("ndk_")

    assert (
        c.delete(
            f"/api/admin/agents/{aid}/keys/{agent['key_id']}", headers=auth()
        ).status_code
        == 204
    )
    assert (
        c.delete(
            f"/api/admin/agents/{aid}/keys/{agent['key_id']}", headers=auth()
        ).status_code
        == 404
    )

    assert c.post(f"/api/admin/agents/{aid}/disable", headers=auth()).status_code == 204
    assert registry.agents[aid]["status"] == "disabled"
    assert c.post(f"/api/admin/agents/{aid}/enable", headers=auth()).status_code == 204
    assert registry.agents[aid]["status"] == "active"
    assert c.post("/api/admin/agents/nope/disable", headers=auth()).status_code == 404
    assert c.post("/api/admin/agents/nope/keys", headers=auth()).status_code == 404


# TC-8
def test_missing_agent_key_or_wrong_token_changes_nothing() -> None:
    registry = FakeRegistry()
    c = client(registry)
    agent_key = make_key().raw
    cases = [
        ({}, 401),  # no token
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": "Basic abc"}, 401),
        ({"Authorization": f"Bearer {agent_key}"}, 403),  # a valid-shaped agent key
    ]
    for headers, status in cases:
        assert (
            c.post("/api/admin/agents", json={"name": "x"}, headers=headers).status_code
            == status
        )
        assert c.get("/api/admin/agents", headers=headers).status_code == status
    assert registry.agents == {}


def test_unset_admin_token_disables_the_routes() -> None:
    c = client(FakeRegistry(), token=None)
    assert c.get("/api/admin/agents", headers=auth()).status_code == 404
    assert (
        c.post("/api/admin/agents", json={"name": "x"}, headers=auth()).status_code
        == 404
    )
