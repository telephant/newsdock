"""TC-1 (API half), TC-2, TC-3 (list), TC-4, TC-5 (routes), TC-15, TC-22."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.agents import GeneratedKey, StoredKey, make_key
from newsdock_api.domain.subscriptions import AdminSubscription, SubscriptionRecord

ADMIN = "admin-token-for-tests"
NOW = datetime(2026, 10, 14, tzinfo=UTC)


class FakeKeys:
    """KeyLookup over a few pre-made agents."""

    def __init__(self) -> None:
        self.keys: dict[str, tuple[GeneratedKey, StoredKey]] = {}

    def add(self, name: str, **flags: bool) -> str:
        key = make_key()
        stored = StoredKey(
            key_id=f"k-{name}", agent_id=f"id-{name}", agent_name=name,
            key_hash=key.key_hash,
            revoked=flags.get("revoked", False),
            agent_active=flags.get("active", True),
        )  # fmt: skip
        self.keys[key.prefix] = (key, stored)
        return key.raw

    def find_key(self, prefix: str) -> StoredKey | None:
        found = self.keys.get(prefix)
        return found[1] if found else None

    def touch_key(self, key_id: str, now: datetime) -> None:
        pass


class FakeStore:
    def __init__(self) -> None:
        self.rows: dict[str, SubscriptionRecord] = {}
        self.owner_names: dict[str, str] = {}

    def create(self, agent_id: str, filter_json: dict[str, str]) -> SubscriptionRecord:
        record = SubscriptionRecord(
            id=f"sub-{len(self.rows) + 1}", agent_id=agent_id,
            filter=filter_json, created_at=NOW,
        )  # fmt: skip
        self.rows[record.id] = record
        self.owner_names[record.id] = agent_id.removeprefix("id-")
        return record

    def list_own(self, agent_id: str) -> list[SubscriptionRecord]:
        return [r for r in self.rows.values() if r.agent_id == agent_id]

    def get_own(self, agent_id: str, sub_id: str) -> SubscriptionRecord | None:
        row = self.rows.get(sub_id)
        return row if row and row.agent_id == agent_id else None

    def delete_own(self, agent_id: str, sub_id: str) -> bool:
        if self.get_own(agent_id, sub_id) is None:
            return False
        del self.rows[sub_id]
        return True

    def count_own(self, agent_id: str) -> int:
        return len(self.list_own(agent_id))

    def exists(self, sub_id: str) -> bool:
        return sub_id in self.rows

    def delete_any(self, sub_id: str) -> bool:
        return self.rows.pop(sub_id, None) is not None

    def list_all(self) -> list[AdminSubscription]:
        return [
            AdminSubscription(**r.model_dump(), agent_name=self.owner_names[r.id])
            for r in self.rows.values()
        ]


class FakeRegistry:
    """The admin routes need a registry object; subscriptions tests do not use it."""

    def create_agent(self, *a: Any, **k: Any) -> Any: ...
    def add_key(self, *a: Any, **k: Any) -> Any: ...
    def revoke_key(self, *a: Any, **k: Any) -> Any: ...
    def set_status(self, *a: Any, **k: Any) -> Any: ...
    def list_agents(self) -> list[Any]:
        return []


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost:5/x")
    monkeypatch.delenv("NEWSDOCK_ADMIN_TOKEN", raising=False)


def make_app(keys: FakeKeys, store: FakeStore, **settings: Any) -> TestClient:
    settings.setdefault("admin_token", ADMIN)
    settings.setdefault("rate_limit_per_minute", 0)
    return TestClient(
        create_app(
            Settings(**settings),
            agents_repo=FakeRegistry(),
            subscriptions_repo=store,
            key_lookup=keys,
        )
    )


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# TC-1 (API half)
def test_create_returns_the_stored_filter() -> None:
    keys, store = FakeKeys(), FakeStore()
    alpha = keys.add("alpha")
    c = make_app(keys, store)
    response = c.post(
        "/api/subscriptions",
        json={"theme": "ECON_*", "domain": "example.com"},
        headers=bearer(alpha),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filter"] == {"theme": "ECON_*", "domain": "example.com"}
    assert body["id"] and "agent_id" not in body
    assert store.rows[body["id"]].agent_id == "id-alpha"


def test_empty_filter_is_allowed() -> None:
    keys, store = FakeKeys(), FakeStore()
    c = make_app(keys, store)
    response = c.post("/api/subscriptions", json={}, headers=bearer(keys.add("alpha")))
    assert response.status_code == 201 and response.json()["filter"] == {}


# TC-2
@pytest.mark.parametrize(
    "body",
    [
        {"unknown": "x"},
        {"theme": 5},
        {"text": "x" * 201},
        {"theme": "ECON_*X"},
        {"domain": ""},
        ["theme"],
    ],
)
def test_invalid_filters_are_422_and_nothing_is_stored(body: Any) -> None:
    keys, store = FakeKeys(), FakeStore()
    c = make_app(keys, store)
    response = c.post("/api/subscriptions", json=body, headers=bearer(keys.add("a")))
    assert response.status_code == 422
    assert store.rows == {}


def test_per_agent_cap_is_409() -> None:
    keys, store = FakeKeys(), FakeStore()
    alpha, beta = keys.add("alpha"), keys.add("beta")
    c = make_app(keys, store, subscriptions_max_per_agent=2)
    for _ in range(2):
        assert (
            c.post("/api/subscriptions", json={}, headers=bearer(alpha)).status_code
            == 201
        )
    over = c.post("/api/subscriptions", json={}, headers=bearer(alpha))
    assert over.status_code == 409 and over.json()["detail"] == "too_many_subscriptions"
    assert (
        c.post("/api/subscriptions", json={}, headers=bearer(beta)).status_code == 201
    )


# TC-3 (list part) and TC-4
def test_list_and_delete_are_scoped_to_the_owner() -> None:
    keys, store = FakeKeys(), FakeStore()
    alpha, beta = keys.add("alpha"), keys.add("beta")
    c = make_app(keys, store)
    mine = c.post(
        "/api/subscriptions", json={"domain": "a.org"}, headers=bearer(alpha)
    ).json()
    theirs = c.post("/api/subscriptions", json={}, headers=bearer(beta)).json()

    listed = c.get("/api/subscriptions", headers=bearer(alpha)).json()
    assert [s["id"] for s in listed] == [mine["id"]]

    assert (
        c.delete(
            f"/api/subscriptions/{theirs['id']}", headers=bearer(alpha)
        ).status_code
        == 404
    )
    assert theirs["id"] in store.rows
    assert (
        c.delete(f"/api/subscriptions/{mine['id']}", headers=bearer(alpha)).status_code
        == 204
    )
    assert mine["id"] not in store.rows


# TC-5 (route part)
def test_routes_need_a_valid_key() -> None:
    keys, store = FakeKeys(), FakeStore()
    revoked = keys.add("old", revoked=True)
    disabled = keys.add("off", active=False)
    unknown = make_key().raw
    c = make_app(keys, store)
    for headers in (
        {},
        {"Authorization": "Bearer junk"},
        bearer(unknown),
        bearer(revoked),
        bearer(disabled),
    ):
        for method, path in (
            ("get", "/api/subscriptions"),
            ("post", "/api/subscriptions"),
            ("delete", "/api/subscriptions/x"),
        ):
            kwargs: dict[str, Any] = {"json": {}} if method == "post" else {}
            response = getattr(c, method)(path, headers=headers, **kwargs)
            assert response.status_code == 401, (headers, method)
    assert store.rows == {}


# TC-22
def test_anonymous_callers_cannot_own_subscriptions() -> None:
    keys, store = FakeKeys(), FakeStore()
    c = make_app(keys, store, auth_required=False)
    for response in (
        c.get("/api/subscriptions"),
        c.post("/api/subscriptions", json={}),
        c.delete("/api/subscriptions/x"),
    ):
        assert response.status_code == 403
        assert response.json()["detail"] == "anonymous_agent"


# TC-15
def test_admin_lists_all_subscriptions_with_agent_names() -> None:
    keys, store = FakeKeys(), FakeStore()
    alpha, beta = keys.add("alpha"), keys.add("beta")
    c = make_app(keys, store)
    c.post("/api/subscriptions", json={"domain": "a.org"}, headers=bearer(alpha))
    c.post("/api/subscriptions", json={"text": "fed"}, headers=bearer(beta))

    ok = c.get("/api/admin/subscriptions", headers=bearer(ADMIN))
    assert ok.status_code == 200
    assert sorted((s["agent_name"], s["filter"]) for s in ok.json()) == [
        ("alpha", {"domain": "a.org"}),
        ("beta", {"text": "fed"}),
    ]
    assert c.get("/api/admin/subscriptions", headers=bearer(alpha)).status_code == 403
    assert c.get("/api/admin/subscriptions").status_code == 401
    off = make_app(keys, store, admin_token=None)
    assert off.get("/api/admin/subscriptions", headers=bearer(ADMIN)).status_code == 401
