"""TC-9 (AC-4, AC-15): credentialed CORS for the web UI (ADR-0021).

The browser (:3000) calls the API (:8000) with the session cookie, so every
response to a listed origin must say `Allow-Credentials: true` with that exact
origin (never `*`), and the preflight must allow the write methods and the two
headers the UI sends (`Content-Type`, `Last-Event-ID`).
"""

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings

LISTED = ["http://127.0.0.1:3000", "http://localhost:3000"]
EVIL = "https://evil.example"


@pytest.fixture(autouse=True)
def offline_db(monkeypatch: pytest.MonkeyPatch) -> None:
    # engine creation does not connect; /api/health degrades to db=False
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost:5/x")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def preflight(
    client: TestClient,
    origin: str,
    method: str,
    headers: str = "content-type",
    path: str = "/api/auth/login",
) -> Response:
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def tokens(value: str | None) -> set[str]:
    return {t.strip().lower() for t in (value or "").split(",") if t.strip()}


@pytest.mark.parametrize("origin", LISTED)
def test_responses_to_a_listed_origin_echo_it_and_allow_credentials(
    client: TestClient, origin: str
) -> None:
    response = client.get("/api/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("origin", LISTED)
def test_preflight_allows_login_with_json_from_a_listed_origin(
    client: TestClient, origin: str
) -> None:
    response = preflight(client, origin, "POST", "content-type")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert {"get", "post", "patch", "delete"} <= tokens(
        response.headers["access-control-allow-methods"]
    )
    assert "content-type" in tokens(response.headers["access-control-allow-headers"])


def test_preflight_allows_the_event_stream_reconnect_header(
    client: TestClient,
) -> None:
    response = preflight(client, LISTED[0], "GET", "last-event-id", path="/api/live")
    assert response.status_code == 200
    assert "last-event-id" in tokens(response.headers["access-control-allow-headers"])


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_preflight_allows_the_user_management_methods(
    client: TestClient, method: str
) -> None:
    response = preflight(client, LISTED[1], method, path="/api/users/x")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LISTED[1]


def test_unlisted_origin_gets_no_cors_grant(client: TestClient) -> None:
    # Starlette may still print `Allow-Credentials: true`; a browser grants nothing
    # without a matching `Allow-Origin`, which an unlisted origin never gets.
    actual = client.get("/api/health", headers={"Origin": EVIL})
    assert "access-control-allow-origin" not in actual.headers
    refused = preflight(client, EVIL, "POST")
    assert refused.status_code == 400
    assert "access-control-allow-origin" not in refused.headers


def test_preflight_refuses_methods_and_headers_outside_the_list(
    client: TestClient,
) -> None:
    assert preflight(client, LISTED[0], "PUT").status_code == 400
    assert preflight(client, LISTED[0], "POST", "x-evil").status_code == 400


def test_the_wildcard_is_never_sent_with_credentials(client: TestClient) -> None:
    for origin in (*LISTED, EVIL):
        for response in (
            client.get("/api/health", headers={"Origin": origin}),
            preflight(client, origin, "POST"),
        ):
            assert response.headers.get("access-control-allow-origin") != "*"


def test_credentials_can_be_switched_off_by_setting() -> None:
    app = create_app(Settings(cors_allow_cookies=False))
    response = TestClient(app).get("/api/health", headers={"Origin": LISTED[0]})
    assert response.headers["access-control-allow-origin"] == LISTED[0]
    assert "access-control-allow-credentials" not in response.headers


def test_origins_come_from_the_setting() -> None:
    client = TestClient(create_app(Settings(cors_origins="https://app.example")))
    ok = client.get("/api/health", headers={"Origin": "https://app.example"})
    assert ok.headers["access-control-allow-origin"] == "https://app.example"
    default = client.get("/api/health", headers={"Origin": LISTED[0]})
    assert "access-control-allow-origin" not in default.headers


def test_a_write_from_an_unlisted_origin_is_refused_by_the_api_too(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "a@x.io", "password": "whatever-123"},
        headers={"Origin": EVIL},
    )
    assert response.status_code == 403 and response.json()["detail"] == "bad_origin"
    assert "access-control-allow-origin" not in response.headers
