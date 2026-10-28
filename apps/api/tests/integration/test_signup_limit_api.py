"""TC-9 to TC-16 (AC-1 to AC-8): the sign-up route and its limiter (Docker)."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.http import create_app
from newsdock_api.adapters.passwords import Argon2Hasher
from newsdock_api.config import Settings
from newsdock_api.domain.signuplimit import SignupLimiter
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PASSWORD = "correct-horse-battery"


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class CountingHasher(Argon2Hasher):
    """Counts password hashes: a refused sign-up must not cost one."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def hash(self, password: str) -> str:
        self.calls += 1
        return super().hash(password)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


class Env:
    def __init__(self, engine: Engine, limiter: SignupLimiter, **settings: object):
        self.engine = engine
        self.limiter = limiter
        self.hasher = CountingHasher()
        self.app = create_app(
            Settings(**settings),  # type: ignore[arg-type]
            hasher=self.hasher,
            signup_limiter=limiter,
        )
        # create_app hashes one dummy password for the login timing defence
        self.baseline = self.hasher.calls

    def client(self, address: str) -> TestClient:
        return TestClient(self.app, client=(address, 50000))

    def signup(self, address: str, email: str, password: str = PASSWORD) -> int:
        response = self.client(address).post(
            "/api/auth/signup", json={"email": email, "password": password}
        )
        return response.status_code

    def users(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM users")).scalar_one())


@pytest.fixture()
def env(engine: Engine) -> Callable[..., Env]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))

    def build(
        per_address: int = 3,
        total: int = 0,
        clock: Clock | None = None,
        **settings: object,
    ) -> Env:
        limiter = SignupLimiter(per_address, total, 3600, clock=clock or Clock())
        return Env(engine, limiter, **settings)

    return build


# TC-9: one address is limited; a refusal costs no hash and no row (AC-1)
def test_one_address_is_refused_after_its_limit(env: Callable[..., Env]) -> None:
    e = env(per_address=3)
    statuses = [e.signup("10.0.0.1", f"u{i}@x.io") for i in range(4)]
    assert statuses == [201, 201, 201, 429]
    refused = e.client("10.0.0.1").post(
        "/api/auth/signup", json={"email": "u9@x.io", "password": PASSWORD}
    )
    assert refused.status_code == 429
    assert refused.json()["detail"] == "too_many_signups"
    assert int(refused.headers["retry-after"]) >= 1
    assert e.users() == 3  # no fourth account
    assert e.hasher.calls - e.baseline == 3  # refused requests never hashed


# TC-10: other addresses are unaffected (AC-2)
def test_another_address_still_signs_up(env: Callable[..., Env]) -> None:
    e = env(per_address=1)
    assert e.signup("10.0.0.1", "a@x.io") == 201
    assert e.signup("10.0.0.1", "b@x.io") == 429
    assert e.signup("10.0.0.2", "c@x.io") == 201


# TC-11: the global cap holds across addresses (AC-3)
def test_the_global_cap_refuses_a_fifth_address(env: Callable[..., Env]) -> None:
    e = env(per_address=10, total=4)
    statuses = [e.signup(f"10.0.1.{i}", f"u{i}@x.io") for i in range(5)]
    assert statuses == [201, 201, 201, 201, 429]
    last = e.client("10.0.1.9").post(
        "/api/auth/signup", json={"email": "z@x.io", "password": PASSWORD}
    )
    assert last.status_code == 429 and int(last.headers["retry-after"]) >= 1


# TC-12: the window recovers (AC-4)
def test_the_same_address_signs_up_again_after_the_window(
    env: Callable[..., Env],
) -> None:
    clock = Clock(1000.0)
    e = env(per_address=1, clock=clock)
    assert e.signup("10.0.0.1", "a@x.io") == 201
    assert e.signup("10.0.0.1", "b@x.io") == 429
    clock.now = 1000.0 + 3600
    assert e.signup("10.0.0.1", "b@x.io") == 201


# TC-13: invalid and closed requests do not consume budget (AC-5)
def test_invalid_requests_are_free_and_a_valid_one_still_passes(
    env: Callable[..., Env],
) -> None:
    e = env(per_address=2)
    bad = [
        e.signup("10.0.0.1", "not-an-email"),
        e.signup("10.0.0.1", "ok@x.io", password="short"),
        e.signup("10.0.0.1", "also bad"),
        e.signup("10.0.0.1", "x@y", password="short"),
        e.signup("10.0.0.1", "", password=""),
    ]
    assert bad == [422] * 5
    assert e.limiter.tracked() == 0
    assert e.signup("10.0.0.1", "good@x.io") == 201


def test_a_closed_signup_answers_403_and_counts_nothing(
    env: Callable[..., Env],
) -> None:
    e = env(per_address=2, auth_signup_open=False)
    statuses = [e.signup("10.0.0.1", f"u{i}@x.io") for i in range(10)]
    assert statuses == [403] * 10
    assert e.limiter.tracked() == 0


# TC-14: a duplicate attempt counts (AC-6)
def test_duplicate_attempts_use_up_the_budget(
    env: Callable[..., Env], engine: Engine
) -> None:
    e = env(per_address=2)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role) "
                "VALUES ('a@x.io', 'x', 'viewer')"
            )
        )
    assert e.signup("10.0.0.1", "a@x.io") == 409
    assert e.signup("10.0.0.1", "a@x.io") == 409
    assert e.signup("10.0.0.1", "new@x.io") == 429


# TC-15: the first account is still the owner under the default limits (AC-7)
def test_the_first_signup_is_the_owner_with_default_limits(
    engine: Engine, env: Callable[..., Env]
) -> None:
    env()  # empties the users table
    app = create_app(Settings())  # built-in limiter from the default settings
    client = TestClient(app, client=("10.0.0.1", 50000))
    response = client.post(
        "/api/auth/signup", json={"email": "first@x.io", "password": PASSWORD}
    )
    assert response.status_code == 201
    assert response.json()["role"] == "owner"


# TC-16: zero switches both limits off (AC-8)
def test_with_both_limits_off_fifty_signups_succeed(env: Callable[..., Env]) -> None:
    e = env(per_address=0, total=0)
    statuses = [e.signup("10.0.0.1", f"u{i}@x.io") for i in range(50)]
    assert statuses == [201] * 50
