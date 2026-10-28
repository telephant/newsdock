"""TC-40 (AC-16) and the reset part of TC-4: owner recovery route (Docker)."""

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
from newsdock_api.domain.agents import make_key
from newsdock_api.domain.loginlimit import LoginLimiter
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-login-test"
OLD = "old-password-12345"
NEW = "brand-new-password-678"
ADMIN = "admin-token-for-tests"
RESET = "/api/admin/users/reset-password"
TOKEN = {"authorization": f"Bearer {ADMIN}"}


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


class Setup:
    def __init__(self, engine: Engine, **kw: object) -> None:
        self.engine = engine
        self.client = TestClient(create_app(Settings(**kw)))  # type: ignore[arg-type]
        self.cookies: dict[str, dict[str, str]] = {}

    def join(self, email: str, role: str | None = None) -> dict[str, str]:
        body = {"email": email, "password": OLD}
        self.client.post("/api/auth/signup", json=body)
        if role:
            with self.engine.begin() as conn:
                conn.execute(
                    text("UPDATE users SET role = :r WHERE email = :e"),
                    {"r": role, "e": email},
                )
        response = self.client.post("/api/auth/login", json=body)
        token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        self.cookies[email] = {"cookie": f"newsdock_session={token}"}
        return self.cookies[email]

    def other(self) -> TestClient:
        return TestClient(self.client.app)

    def login(self, email: str, password: str) -> int:
        return (
            self.other()
            .post("/api/auth/login", json={"email": email, "password": password})
            .status_code
        )


@pytest.fixture()
def setup(engine: Engine) -> Callable[..., Setup]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        conn.execute(text("TRUNCATE agents CASCADE"))

    def build(**kw: object) -> Setup:
        return Setup(engine, **kw)

    return build


def reset(
    s: Setup, email: str, password: str = NEW, headers: dict[str, str] | None = None
) -> int:
    response = s.other().post(
        RESET, json={"email": email, "password": password}, headers=headers or TOKEN
    )
    return response.status_code


def test_the_token_resets_the_password_and_ends_the_sessions(
    setup: Callable[..., Setup],
) -> None:
    s = setup()
    owner = s.join("owner@x.io")
    viewer = s.join("viewer@x.io")
    assert s.other().get("/api/auth/me", headers=owner).status_code == 200

    assert reset(s, "owner@x.io") == 204
    assert s.login("owner@x.io", OLD) == 401
    assert s.other().get("/api/auth/me", headers=owner).status_code == 401
    assert s.login("owner@x.io", NEW) == 200
    # nobody else is touched
    assert s.other().get("/api/auth/me", headers=viewer).status_code == 200
    assert s.login("viewer@x.io", OLD) == 200


def test_the_email_is_matched_after_normalizing(setup: Callable[..., Setup]) -> None:
    s = setup()
    s.join("owner@x.io")
    assert reset(s, "  OWNER@X.IO ") == 204
    assert s.login("owner@x.io", NEW) == 200


def test_sessions_cannot_reset_passwords(setup: Callable[..., Setup]) -> None:
    s = setup()
    owner = s.join("owner@x.io")
    admin = s.join("admin@x.io", "admin")
    for who in (owner, admin):
        assert reset(s, "owner@x.io", headers=who) == 403
    assert s.login("owner@x.io", OLD) == 200  # unchanged


def test_agent_keys_and_anonymous_callers_are_refused(
    setup: Callable[..., Setup], engine: Engine
) -> None:
    s = setup()
    s.join("owner@x.io")
    key = make_key()
    SqlAgentsRepo(engine).create_agent("alpha", key, None)
    assert reset(s, "owner@x.io", headers={"authorization": f"Bearer {key.raw}"}) == 403
    assert reset(s, "owner@x.io", headers={"authorization": "Bearer wrong"}) == 401
    anon = s.other().post(RESET, json={"email": "owner@x.io", "password": NEW})
    assert anon.status_code == 401
    assert s.login("owner@x.io", OLD) == 200


def test_bad_requests(setup: Callable[..., Setup]) -> None:
    s = setup()
    s.join("owner@x.io")
    assert reset(s, "nobody@x.io") == 404
    assert reset(s, "owner@x.io", "short") == 422
    assert reset(s, "owner@x.io", "x" * 129) == 422
    assert reset(s, "not-an-email") == 422
    assert s.login("owner@x.io", OLD) == 200  # still the old password
    bare = s.other().post(RESET, headers=TOKEN)
    assert bare.status_code == 422


def test_without_a_configured_token_the_route_does_not_exist(
    setup: Callable[..., Setup], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEWSDOCK_ADMIN_TOKEN")
    s = setup()
    owner = s.join("owner@x.io")
    for headers in (TOKEN, owner, {}):
        assert reset(s, "owner@x.io", headers=headers) == 404
    assert s.login("owner@x.io", OLD) == 200


def test_a_reset_also_lifts_the_login_lockout(setup: Callable[..., Setup]) -> None:
    class Clock:
        def __call__(self) -> float:
            return 1000.0

    limiter = LoginLimiter(3, 900, clock=Clock())
    s = Setup.__new__(Setup)  # build the app by hand to inject the limiter
    s.engine = setup().engine
    s.client = TestClient(create_app(Settings(), login_limiter=limiter))
    s.cookies = {}
    s.join("owner@x.io")
    for _ in range(3):
        assert s.login("owner@x.io", "wrong-password-1") == 401
    assert s.login("owner@x.io", OLD) == 429  # locked out: the recovery scenario
    assert reset(s, "owner@x.io") == 204
    assert s.login("owner@x.io", NEW) == 200


def test_the_reset_does_not_log_secrets(
    setup: Callable[..., Setup], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    s = setup()
    owner = s.join("owner@x.io")
    cookie = owner["cookie"].split("=", 1)[1]
    assert reset(s, "owner@x.io") == 204
    logged = "\n".join(r.getMessage() + str(r.exc_text or "") for r in caplog.records)
    for secret in (NEW, OLD, cookie, ADMIN):
        assert secret not in logged
