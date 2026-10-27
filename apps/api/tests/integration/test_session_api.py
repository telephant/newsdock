"""TC-8 (/me), TC-10, TC-14, TC-15, TC-16, TC-17, TC-35 token half (Docker)."""

import logging
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.accounts import hash_token
from newsdock_api.domain.agents import make_key
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-login-test"
PASSWORD = "correct-horse-battery"
ADMIN = "admin-token-for-tests"
WEB = "http://127.0.0.1:3000"  # a listed origin (default cors_origins)
ARTICLE = "a" * 64


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


@pytest.fixture()
def make_client(engine: Engine) -> Callable[..., TestClient]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        conn.execute(text("TRUNCATE agents CASCADE"))
        conn.execute(text("DELETE FROM articles"))
        conn.execute(
            text(
                "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                "domain, published_at, themes, persons, orgs, tone, tone_pos, "
                "tone_neg, tone_polarity, word_count) VALUES (:h, 'r', "
                "'20261027120000', 'https://example.com/a', 'A title', "
                "'example.com', now(), ARRAY['ECON_X'], ARRAY[]::text[], "
                "ARRAY[]::text[], 0, 0, 0, 0, 1)"
            ),
            {"h": ARTICLE},
        )

    def build(**overrides: object) -> TestClient:
        return TestClient(create_app(Settings(**overrides)))  # type: ignore[arg-type]

    return build


def _join(client: TestClient, email: str, role: str | None = None) -> str:
    """Sign up + log in; returns the raw cookie value. First account is the owner."""
    client.post("/api/auth/signup", json={"email": email, "password": PASSWORD})
    response = client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    return response.headers["set-cookie"].split(";")[0].split("=", 1)[1]


def _viewer(client: TestClient, email: str = "viewer@x.io") -> str:
    """A viewer cookie; makes sure an owner exists first."""
    client.post("/api/auth/signup", json={"email": "owner@x.io", "password": PASSWORD})
    return _join(client, email)


def _with_cookie(token: str) -> dict[str, str]:
    return {"cookie": f"newsdock_session={token}"}


# ---- TC-8 (/me half) ------------------------------------------------------------
def test_me_returns_the_logged_in_user(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    _join(client, "owner@x.io")
    body = client.get("/api/auth/me").json()
    assert body["email"] == "owner@x.io" and body["role"] == "owner"
    assert set(body) == {"id", "email", "role"}


def test_me_without_a_session_is_401(make_client: Callable[..., TestClient]) -> None:
    assert make_client().get("/api/auth/me").status_code == 401


# ---- TC-14 ------------------------------------------------------------------------
def test_logout_ends_the_session_and_clears_the_cookie(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    token = _viewer(client)
    assert client.get("/api/auth/me").status_code == 200
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    with engine.connect() as conn:
        left = conn.execute(text("SELECT token_hash FROM sessions")).scalars().all()
    assert hash_token(token) not in left
    fresh = make_client()  # no jar: replay the old cookie by hand
    for path in ("/api/auth/me", "/api/articles"):
        assert fresh.get(path, headers=_with_cookie(token)).status_code == 401
    again = fresh.post("/api/auth/logout", headers=_with_cookie(token))
    assert again.status_code == 204  # idempotent


def test_logout_without_any_cookie_is_401(
    make_client: Callable[..., TestClient],
) -> None:
    assert make_client().post("/api/auth/logout").status_code == 401


# ---- TC-15 ------------------------------------------------------------------------
def test_idle_and_absolute_expiry_end_the_session(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    token = _viewer(client)
    assert client.get("/api/auth/me", headers=_with_cookie(token)).status_code == 200
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET last_seen_at = now() - interval '13 hours'")
        )
    for path in ("/api/auth/me", "/api/articles"):
        response = make_client().get(path, headers=_with_cookie(token))
        assert response.status_code == 401, path
    token2 = _join(client, "viewer@x.io")  # logs in again: a fresh session
    assert (
        make_client().get("/api/auth/me", headers=_with_cookie(token2)).status_code
        == 200
    )
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET expires_at = now() - interval '1 second'")
        )
    assert (
        make_client().get("/api/auth/me", headers=_with_cookie(token2)).status_code
        == 401
    )


def test_login_removes_expired_rows(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    old = _viewer(client)
    with engine.begin() as conn:
        conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 day'"))
    _join(client, "viewer@x.io")
    with engine.connect() as conn:
        left = conn.execute(text("SELECT token_hash FROM sessions")).scalars().all()
    assert hash_token(old) not in left


def test_an_active_session_has_its_last_seen_refreshed(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    token = _viewer(client)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET last_seen_at = now() - interval '10 minutes'")
        )
    assert client.get("/api/auth/me", headers=_with_cookie(token)).status_code == 200
    with engine.connect() as conn:
        age = conn.execute(
            text(
                "SELECT extract(epoch FROM now() - last_seen_at) FROM sessions "
                "WHERE token_hash = :h"
            ),
            {"h": hash_token(token)},
        ).scalar_one()
    assert float(age) < 60


# ---- TC-16 ------------------------------------------------------------------------
def test_article_reads_need_a_session_or_an_agent_key(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    cookie = _with_cookie(_viewer(client))
    agents = SqlAgentsRepo(engine)
    good = make_key()
    agents.create_agent("alpha", good)
    revoked = make_key()
    created = agents.create_agent("beta", revoked)
    agents.revoke_key(created.id, created.key_id)

    anon = make_client()
    for path in ("/api/articles", f"/api/articles/{ARTICLE}"):
        assert anon.get(path).status_code == 401, path
        assert anon.get(path, headers=cookie).status_code == 200, path
        bearer = {"authorization": f"Bearer {good.raw}"}
        assert anon.get(path, headers=bearer).status_code == 200, path
        bad = {"authorization": f"Bearer {revoked.raw}"}
        assert anon.get(path, headers=bad).status_code == 401, path
        forged = {"cookie": "newsdock_session=forged"}
        assert anon.get(path, headers=forged).status_code == 401, path
    assert anon.get("/api/health").status_code == 200


def test_a_bad_key_does_not_fall_back_to_a_valid_cookie(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    cookie = _viewer(client)
    agents = SqlAgentsRepo(engine)
    key = make_key()
    created = agents.create_agent("beta", key)
    agents.revoke_key(created.id, created.key_id)
    headers = {**_with_cookie(cookie), "authorization": f"Bearer {key.raw}"}
    assert make_client().get("/api/articles", headers=headers).status_code == 401


def test_reads_are_open_when_auth_is_not_required(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(auth_required=False)
    assert client.get("/api/articles").status_code == 200
    assert client.get(f"/api/articles/{ARTICLE}").status_code == 200
    # even a forged cookie does not matter in dev mode
    forged = {"cookie": "newsdock_session=forged"}
    assert client.get("/api/articles", headers=forged).status_code == 200


def test_the_401_carries_cors_headers_so_the_ui_can_read_it(
    make_client: Callable[..., TestClient],
) -> None:
    response = make_client().get("/api/articles", headers={"origin": WEB})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == WEB


# ---- TC-10 ------------------------------------------------------------------------
def test_writes_must_be_json_and_from_a_listed_origin(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    body = '{"email": "a@x.io", "password": "correct-horse-battery"}'
    plain = client.post(
        "/api/auth/login", content=body, headers={"content-type": "text/plain"}
    )
    assert plain.status_code == 415
    form = client.post("/api/auth/login", data={"email": "a", "password": "b"})
    assert form.status_code == 415
    evil = client.post(
        "/api/auth/login",
        json={"email": "a@x.io", "password": PASSWORD},
        headers={"origin": "http://evil.example"},
    )
    assert evil.status_code == 403 and evil.json()["detail"] == "bad_origin"
    for origin in (WEB, None):  # a listed origin and no Origin at all are accepted
        headers = {"origin": origin} if origin else {}
        ok = client.post(
            "/api/auth/login",
            json={"email": "nobody@x.io", "password": PASSWORD},
            headers=headers,
        )
        assert ok.status_code == 401  # reached the handler: wrong credentials


def test_a_bodyless_post_from_a_foreign_origin_is_refused(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    token = _viewer(client)
    headers = {**_with_cookie(token), "origin": "http://evil.example"}
    assert make_client().post("/api/auth/logout", headers=headers).status_code == 403
    # the session survived the forged logout
    assert (
        make_client().get("/api/auth/me", headers=_with_cookie(token)).status_code
        == 200
    )


def test_reads_from_a_foreign_origin_are_not_blocked_by_the_write_guard(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    token = _viewer(client)
    headers = {**_with_cookie(token), "origin": "http://evil.example"}
    # CORS (browser side) governs cross-origin reads; the guard only covers writes
    assert make_client().get("/api/articles", headers=headers).status_code == 200


# ---- TC-35 (token half) -----------------------------------------------------------
def test_the_admin_token_is_not_a_user_session(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    bearer = {"authorization": f"Bearer {ADMIN}"}
    assert client.get("/api/auth/me", headers=bearer).status_code == 401
    assert client.post("/api/auth/logout", headers=bearer).status_code == 401
    assert client.get("/api/articles", headers=bearer).status_code == 401


# ---- TC-4 (logout part) -----------------------------------------------------------
def test_logout_does_not_log_the_cookie(
    make_client: Callable[..., TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client()
    token = _viewer(client)
    client.get("/api/auth/me")
    client.post("/api/auth/logout")
    make_client().get("/api/articles", headers={"cookie": "newsdock_session=forged"})
    logged = "\n".join(r.getMessage() + str(r.exc_text or "") for r in caplog.records)
    assert token not in logged and hash_token(token) not in logged
    assert "forged" not in logged and PASSWORD not in logged
