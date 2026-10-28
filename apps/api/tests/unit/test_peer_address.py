"""TC-8 (AC-2): the route can see the peer address a test client presents.

Spike for signup-rate-limit: the sign-up route tests need a different peer address
per client, so prove `TestClient(app, client=(host, port))` reaches
`request.client.host`.
"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from newsdock_api.domain.signuplimit import UNKNOWN_ADDRESS

app = FastAPI()


@app.get("/who")
def who(request: Request) -> dict[str, str]:
    return {"host": request.client.host if request.client else UNKNOWN_ADDRESS}


def test_each_test_client_has_its_own_peer_address() -> None:
    first = TestClient(app, client=("10.0.0.7", 50000))
    second = TestClient(app, client=("10.0.0.8", 50001))
    assert first.get("/who").json() == {"host": "10.0.0.7"}
    assert second.get("/who").json() == {"host": "10.0.0.8"}


def test_a_missing_peer_address_shares_one_key() -> None:
    assert UNKNOWN_ADDRESS == "unknown"
