"""The browser UI (:3000) must be allowed to call the REST API (:8000)."""

import pytest
from fastapi.testclient import TestClient
from newsdock_api.adapters.http import create_app

ORIGIN = "http://127.0.0.1:3000"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # engine creation does not connect; /api/health degrades to db=False
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost:5/x")
    return TestClient(create_app())


def test_rest_responses_carry_cors_header_for_the_web_origin(
    client: TestClient,
) -> None:
    response = client.get("/api/health", headers={"Origin": ORIGIN})
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_preflight_allows_get_from_the_web_origin(client: TestClient) -> None:
    response = client.options(
        "/api/articles",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_unknown_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
