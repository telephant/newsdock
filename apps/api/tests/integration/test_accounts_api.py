"""TC-1, TC-4, TC-7, TC-8 (cookie half), TC-12, TC-33: sign-up and login (Docker)."""

import logging
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.accounts import hash_token
from newsdock_api.domain.loginlimit import LoginLimiter
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-login-test"
PASSWORD = "correct-horse-battery"


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

    def build(limiter: LoginLimiter | None = None, **overrides: object) -> TestClient:
        settings = Settings(**overrides)  # type: ignore[arg-type]
        return TestClient(create_app(settings, login_limiter=limiter))

    return build


def _signup(client: TestClient, email: str, password: str = PASSWORD) -> object:
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def _login(client: TestClient, email: str, password: str = PASSWORD) -> object:
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)


# ---- TC-1 ----------------------------------------------------------------------
def test_signup_creates_a_viewer_with_an_argon2id_hash(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    assert _signup(client, "owner@x.io").status_code == 201  # type: ignore[attr-defined]
    response = _signup(client, "a@x.io")
    assert response.status_code == 201  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["email"] == "a@x.io" and body["role"] == "viewer"
    assert not any("password" in key or "hash" in key for key in body)
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT role, password_hash FROM users WHERE email = 'a@x.io'")
        ).one()
    assert stored.role == "viewer"
    assert stored.password_hash.startswith("$argon2id$")
    assert PASSWORD not in stored.password_hash


def test_the_first_signup_is_the_owner(
    make_client: Callable[..., TestClient],
) -> None:
    response = _signup(make_client(), "first@x.io")
    assert response.json()["role"] == "owner"  # type: ignore[attr-defined]


# ---- TC-7 ----------------------------------------------------------------------
def test_bad_signups_are_rejected_and_create_nothing(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    assert _signup(client, "a@x.io").status_code == 201  # type: ignore[attr-defined]
    before = _count(engine, "users")
    cases = [
        ("A@X.IO ", PASSWORD, 409),
        ("b@x.io", "x" * 9, 422),
        ("b@x.io", "x" * 129, 422),
        ("not-an-email", PASSWORD, 422),
    ]
    for email, password, status in cases:
        response = _signup(client, email, password)
        assert response.status_code == status, (email, len(password))  # type: ignore[attr-defined]
    assert _count(engine, "users") == before


def test_signup_closed_returns_403_and_creates_nothing(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client(auth_signup_open=False)
    response = _signup(client, "fresh@x.io")
    assert response.status_code == 403  # type: ignore[attr-defined]
    assert response.json()["detail"] == "signup_closed"  # type: ignore[attr-defined]
    assert _count(engine, "users") == 0


# ---- TC-8 (cookie half; /me is checked in T-05) ---------------------------------
def test_login_sets_an_httponly_lax_cookie_and_stores_only_a_hash(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    _signup(client, "a@x.io")
    response = _login(client, "A@x.io")
    assert response.status_code == 200  # type: ignore[attr-defined]
    assert response.json()["email"] == "a@x.io"  # type: ignore[attr-defined]
    cookie = response.headers["set-cookie"]  # type: ignore[attr-defined]
    parts = {p.strip().lower() for p in cookie.split(";")}
    assert "httponly" in parts and "samesite=lax" in parts and "path=/" in parts
    assert "max-age=604800" in parts  # 7 days
    assert "secure" not in parts
    token = cookie.split(";")[0].split("=", 1)[1]
    assert token and token != hash_token(token)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT token_hash FROM sessions")).scalars().all()
    assert rows == [hash_token(token)]  # the cookie value itself is never stored


def test_cookie_is_secure_when_configured(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(auth_cookie_secure=True, auth_cookie_name="custom_sid")
    _signup(client, "a@x.io")
    cookie = _login(client, "a@x.io").headers["set-cookie"]  # type: ignore[attr-defined]
    assert cookie.startswith("custom_sid=")
    assert "secure" in {p.strip().lower() for p in cookie.split(";")}


# ---- TC-12 ---------------------------------------------------------------------
def test_wrong_password_and_unknown_email_look_identical(
    engine: Engine, make_client: Callable[..., TestClient]
) -> None:
    client = make_client()
    _signup(client, "a@x.io")
    wrong = _login(client, "a@x.io", "wrong-password-1")
    unknown = _login(client, "b@x.io", "wrong-password-1")
    assert wrong.status_code == unknown.status_code == 401  # type: ignore[attr-defined]
    assert wrong.content == unknown.content  # type: ignore[attr-defined]
    assert "set-cookie" not in wrong.headers  # type: ignore[attr-defined]
    assert _count(engine, "sessions") == 0


def test_malformed_login_bodies_are_422_not_500(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    assert client.post("/api/auth/login", json={}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "a@x.io"}).status_code == 422
    huge = {"email": "a@x.io", "password": "x" * 5000}
    assert client.post("/api/auth/login", json=huge).status_code == 422


# ---- TC-33 ---------------------------------------------------------------------
class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_lockout_blocks_even_the_right_password_until_the_window_ends(
    make_client: Callable[..., TestClient],
) -> None:
    clock = Clock()
    client = make_client(
        limiter=LoginLimiter(3, 60, clock=clock), auth_login_max_failures=3
    )
    _signup(client, "a@x.io")
    _signup(client, "b@x.io")
    for _ in range(3):
        assert _login(client, "a@x.io", "wrong-password-1").status_code == 401  # type: ignore[attr-defined]
    locked = _login(client, "a@x.io")  # the right password
    assert locked.status_code == 429  # type: ignore[attr-defined]
    assert int(locked.headers["retry-after"]) >= 1  # type: ignore[attr-defined]
    assert locked.json()["detail"] == "too_many_attempts"  # type: ignore[attr-defined]
    assert _login(client, "b@x.io").status_code == 200  # type: ignore[attr-defined]
    clock.now += 61
    assert _login(client, "a@x.io").status_code == 200  # type: ignore[attr-defined]


def test_success_resets_the_failure_counter(
    make_client: Callable[..., TestClient],
) -> None:
    limiter = LoginLimiter(3, 60, clock=Clock())
    client = make_client(limiter=limiter)
    _signup(client, "a@x.io")
    for _ in range(2):
        _login(client, "a@x.io", "wrong-password-1")
    assert _login(client, "a@x.io").status_code == 200  # type: ignore[attr-defined]
    for _ in range(2):  # a fresh budget after the success
        assert _login(client, "a@x.io", "wrong-password-1").status_code == 401  # type: ignore[attr-defined]


def test_unknown_emails_are_throttled_like_known_ones(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client(limiter=LoginLimiter(2, 60, clock=Clock()))
    for _ in range(2):
        assert _login(client, "ghost@x.io", "wrong-password-1").status_code == 401  # type: ignore[attr-defined]
    assert _login(client, "ghost@x.io", "wrong-password-1").status_code == 429  # type: ignore[attr-defined]


# ---- TC-4 (sign-up and login part; logout and reset are added later) ------------
def test_no_secret_reaches_the_logs(
    engine: Engine,
    make_client: Callable[..., TestClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client()
    _signup(client, "log@x.io", "very-secret-pass-1")
    _login(client, "log@x.io", "bad-secret-pass-2")
    response = _login(client, "log@x.io", "very-secret-pass-1")
    token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]  # type: ignore[attr-defined]
    with engine.connect() as conn:
        stored_hash = conn.execute(
            text("SELECT password_hash FROM users WHERE email = 'log@x.io'")
        ).scalar_one()
    logged = "\n".join(
        record.getMessage() + " " + str(record.exc_text or "")
        for record in caplog.records
    )
    for secret in (
        "very-secret-pass-1",
        "bad-secret-pass-2",
        token,
        hash_token(token),
        stored_hash,
    ):
        assert secret not in logged
