"""TC-1, TC-2, TC-4 to TC-15, TC-18 (AC-1 to AC-14, AC-17): the reset routes (Docker).

No real mail: `FakeMailer` records messages, can fail and can block on an event.
Expiry uses the injected `reset_clock`; the one live-server test (AC-1) exists because
Starlette's TestClient finishes background tasks before it returns.
"""

import logging
import re
import socket
import statistics
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings
from newsdock_api.domain.mail import MailError
from newsdock_api.domain.passwordreset import hash_code
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
SECRET = "test-reset-secret-0123456789abcdef0123"
SMTP_PASSWORD = "smtp-password-for-tests"
PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-brand-new-password"
GENERIC = {"ok": True}
CODE_RE = re.compile(r"\b(\d{6})\b")


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = False
        self.gate: threading.Event | None = None  # when set, send waits for it
        self.started = threading.Event()
        self.finished = threading.Event()
        self.delay = 0.0

    def send(self, to: str, subject: str, body: str) -> None:
        self.started.set()
        if self.gate is not None:
            self.gate.wait(30)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise MailError("mail send failed: SMTPRecipientsRefused")
        self.sent.append((to, subject, body))
        self.finished.set()

    def code_for(self, to: str) -> str:
        bodies = [b for t, _, b in self.sent if t == to]
        match = CODE_RE.search(bodies[-1])
        assert match, bodies[-1]
        return match.group(1)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
        smtp_host="smtp.example.test", mail_from="noreply@example.test",
        reset_code_secret=SECRET, smtp_password=SMTP_PASSWORD,
        auth_signup_max_per_address=0, auth_signup_max_total=0,
        auth_login_max_failures=0, rate_limit_per_minute=0,
    )  # fmt: skip
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class Env:
    def __init__(self, engine: Engine, **overrides: object) -> None:
        self.engine = engine
        self.mailer = FakeMailer()
        self.clock = Clock()
        self.app = create_app(
            settings(**overrides), mailer=self.mailer, reset_clock=self.clock
        )

    def client(self, address: str = "10.0.0.1") -> TestClient:
        return TestClient(self.app, client=(address, 50000))

    def signup(self, email: str, password: str = PASSWORD) -> str:
        r = self.client().post(
            "/api/auth/signup", json={"email": email, "password": password}
        )
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    def login(self, email: str, password: str = PASSWORD) -> TestClient:
        c = self.client()
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return c

    def forgot(self, email: str, address: str = "10.0.0.1") -> Any:
        return self.client(address).post(
            "/api/auth/forgot-password", json={"email": email}
        )

    def reset(
        self,
        email: str,
        code: str,
        password: str = NEW_PASSWORD,
        address: str = "10.0.0.1",
    ) -> Any:
        return self.client(address).post(
            "/api/auth/reset-password",
            json={"email": email, "code": code, "password": password},
        )

    def rows(self) -> list[tuple[str, int]]:
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT code_hash, attempts FROM password_resets")
            )
            return [(str(r[0]), int(r[1])) for r in result]

    def can_login(self, email: str, password: str) -> bool:
        r = self.client().post(
            "/api/auth/login", json={"email": email, "password": password}
        )
        return r.status_code == 200


@pytest.fixture()
def env(engine: Engine) -> Callable[..., Env]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))

    def build(**overrides: object) -> Env:
        return Env(engine, **overrides)

    return build


# TC-2: one mail with a 6-digit code and the lifetime, only the keyed hash stored (AC-2)
def test_a_known_email_gets_one_mail_and_only_the_hash_is_stored(
    env: Callable[..., Env],
) -> None:
    e = env()
    user_id = e.signup("ada@example.com")
    r = e.forgot("ada@example.com")
    assert r.status_code == 202 and r.json() == GENERIC
    assert len(e.mailer.sent) == 1
    to, _subject, body = e.mailer.sent[0]
    assert to == "ada@example.com"
    code = e.mailer.code_for("ada@example.com")
    assert re.fullmatch(r"\d{6}", code)
    assert "15 minutes" in body and "http" not in body
    [(stored, attempts)] = e.rows()
    assert re.fullmatch(r"[0-9a-f]{64}", stored) and stored != code
    assert stored == hash_code(SECRET, user_id, code) and attempts == 0


# TC-4: unknown email is indistinguishable and sends nothing (AC-3)
def test_an_unknown_email_gets_the_same_answer_and_nothing_is_sent(
    env: Callable[..., Env],
) -> None:
    e = env()
    e.signup("ada@example.com")
    known = e.forgot("ada@example.com")
    sent_before = len(e.mailer.sent)
    unknown = e.forgot("nobody@example.com")
    assert (unknown.status_code, unknown.json()) == (known.status_code, known.json())
    assert len(e.mailer.sent) == sent_before
    assert all(t != "nobody@example.com" for t, _, _ in e.mailer.sent)
    assert len(e.rows()) == 1  # only ada's


def test_a_malformed_email_is_422_before_anything_happens(
    env: Callable[..., Env],
) -> None:
    e = env()
    r = e.forgot("not-an-email")
    assert r.status_code == 422 and r.json()["detail"] == "invalid_email"
    assert e.mailer.sent == [] and e.rows() == []


# TC-5: the correct code sets the password (AC-4)
def test_the_correct_code_sets_the_new_password(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    code = e.mailer.code_for("ada@example.com")
    r = e.reset("ada@example.com", code)
    assert r.status_code == 204
    assert e.can_login("ada@example.com", NEW_PASSWORD)
    assert not e.can_login("ada@example.com", PASSWORD)


def test_the_email_is_matched_case_insensitively(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.forgot("  Ada@Example.COM ")
    code = e.mailer.code_for("ada@example.com")
    assert e.reset("ADA@example.com", code).status_code == 204


# TC-6: a code works once (AC-5)
def test_a_used_code_is_refused_and_the_password_stays(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    code = e.mailer.code_for("ada@example.com")
    assert e.reset("ada@example.com", code).status_code == 204
    again = e.reset("ada@example.com", code, password="another-valid-password")
    assert again.status_code == 400
    assert again.json()["detail"] == "invalid_or_expired_code"
    assert e.can_login("ada@example.com", NEW_PASSWORD)
    assert not e.can_login("ada@example.com", "another-valid-password")


# TC-7: wrong codes get one uniform error; the code dies at the cap (AC-6)
def test_wrong_codes_are_uniform_and_the_code_dies_after_the_cap(
    env: Callable[..., Env],
) -> None:
    e = env(auth_reset_max_attempts=5)
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    code = e.mailer.code_for("ada@example.com")
    wrong = "000000" if code != "000000" else "111111"
    unknown = e.reset("nobody@example.com", wrong)
    answers = [e.reset("ada@example.com", wrong) for _ in range(5)]
    answers.append(e.reset("ada@example.com", code))  # right, but the cap is spent
    for a in answers:
        assert a.status_code == 400
        assert a.json() == unknown.json() == {"detail": "invalid_or_expired_code"}
    assert e.rows()[0][1] == 5
    assert e.can_login("ada@example.com", PASSWORD)


def test_a_malformed_code_is_refused_without_counting(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    for bad in ("12345", "1234567", "12345a", "١٢٣٤٥٦", "123456\n", ""):
        r = e.reset("ada@example.com", bad)
        assert r.status_code == 400, bad
        assert r.json()["detail"] == "invalid_or_expired_code"
    assert e.rows()[0][1] == 0


# TC-8: an expired code is refused (AC-7)
def test_an_expired_code_is_refused(env: Callable[..., Env]) -> None:
    e = env(auth_reset_code_minutes=15)
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    code = e.mailer.code_for("ada@example.com")
    e.clock.now += timedelta(minutes=15, seconds=1)
    r = e.reset("ada@example.com", code)
    assert r.status_code == 400 and r.json()["detail"] == "invalid_or_expired_code"
    assert e.can_login("ada@example.com", PASSWORD)


# TC-9: a newer request replaces the older code (AC-8)
def test_a_newer_code_replaces_the_older_one(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    first = e.mailer.code_for("ada@example.com")
    e.forgot("ada@example.com")
    second = e.mailer.code_for("ada@example.com")
    assert len(e.rows()) == 1
    if first != second:  # one chance in a million that they are equal
        assert e.reset("ada@example.com", first).status_code == 400
    assert e.reset("ada@example.com", second).status_code == 204


# TC-10: a reset ends every session of the user, not others' (AC-9)
def test_a_reset_ends_all_sessions_of_the_user_only(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.signup("bob@example.com")
    ada1, ada2 = e.login("ada@example.com"), e.login("ada@example.com")
    bob = e.login("bob@example.com")
    e.forgot("ada@example.com")
    assert (
        e.reset("ada@example.com", e.mailer.code_for("ada@example.com")).status_code
        == 204
    )
    assert ada1.get("/api/auth/me").status_code == 401
    assert ada2.get("/api/auth/me").status_code == 401
    assert bob.get("/api/auth/me").status_code == 200


# TC-11: a weak password is refused and keeps the code (AC-10)
def test_a_weak_password_is_422_and_the_code_survives(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    code = e.mailer.code_for("ada@example.com")
    r = e.reset("ada@example.com", code, password="abc")
    assert r.status_code == 422 and r.json()["detail"] == "invalid_password"
    assert e.rows()[0][1] == 0
    assert e.reset("ada@example.com", code).status_code == 204


def test_a_reset_clears_the_login_lockout(env: Callable[..., Env]) -> None:
    e = env(auth_login_max_failures=2)
    e.signup("ada@example.com")
    for _ in range(2):
        e.client().post(
            "/api/auth/login",
            json={"email": "ada@example.com", "password": "wrong-one"},
        )
    locked = e.client().post(
        "/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}
    )
    assert locked.status_code == 429
    e.forgot("ada@example.com")
    assert (
        e.reset("ada@example.com", e.mailer.code_for("ada@example.com")).status_code
        == 204
    )
    assert e.can_login("ada@example.com", NEW_PASSWORD)


# TC-12: requests are limited per email, known or unknown (AC-11)
@pytest.mark.parametrize("known", [True, False])
def test_requests_are_limited_per_email(env: Callable[..., Env], known: bool) -> None:
    e = env(auth_reset_max_per_email=3, auth_reset_max_per_address=0)
    if known:
        e.signup("ada@example.com")
    statuses = [e.forgot("ada@example.com") for _ in range(4)]
    assert [s.status_code for s in statuses] == [202, 202, 202, 429]
    last = statuses[-1]
    assert last.json()["detail"] == "too_many_reset_requests"
    assert int(last.headers["retry-after"]) >= 1
    assert len(e.mailer.sent) == (3 if known else 0)


# TC-13: requests are limited per client address (AC-12)
def test_requests_are_limited_per_address(env: Callable[..., Env]) -> None:
    e = env(auth_reset_max_per_address=3, auth_reset_max_per_email=0)
    for name in ("a", "b", "c"):
        e.signup(f"{name}@example.com")
    statuses = [e.forgot(f"{n}@example.com") for n in ("a", "b", "c", "a")]
    assert [s.status_code for s in statuses] == [202, 202, 202, 429]
    assert statuses[-1].json()["detail"] == "too_many_reset_requests"
    assert int(statuses[-1].headers["retry-after"]) >= 1
    assert len(e.mailer.sent) == 3
    assert e.forgot("a@example.com", address="10.0.0.2").status_code == 202


# TC-14: without SMTP the feature is off (AC-13)
@pytest.mark.parametrize(
    "off", [{"smtp_host": ""}, {"mail_from": ""}, {"reset_code_secret": None}]
)
def test_the_feature_is_off_without_host_sender_or_secret(
    env: Callable[..., Env], off: dict[str, object]
) -> None:
    e = env(**off)
    e.signup("ada@example.com")
    f = e.forgot("ada@example.com")
    r = e.reset("ada@example.com", "123456")
    for answer in (f, r):
        assert answer.status_code == 503
        assert answer.json()["detail"] == "password_reset_unavailable"
    assert e.rows() == [] and e.mailer.sent == []
    options = e.client().get("/api/auth/options")
    assert options.status_code == 200
    assert options.json() == {"password_reset_enabled": False}


def test_options_says_true_when_the_feature_is_on(env: Callable[..., Env]) -> None:
    assert env().client().get("/api/auth/options").json() == {
        "password_reset_enabled": True
    }


# TC-15: a mail failure changes nothing for the user and leaks nothing (AC-14)
def test_a_mail_failure_is_invisible_discards_the_code_and_logs_no_secret(
    env: Callable[..., Env], caplog: pytest.LogCaptureFixture
) -> None:
    e = env()
    e.signup("ada@example.com")
    e.mailer.fail = True
    with caplog.at_level(logging.DEBUG):
        r = e.forgot("ada@example.com")
        # also run a normal request and a reset so their log lines are inspected
        e.mailer.fail = False
        e.forgot("ada@example.com")
        code = e.mailer.code_for("ada@example.com")
        e.reset("ada@example.com", code)
        e.reset("ada@example.com", "654321")
    assert r.status_code == 202 and r.json() == GENERIC
    assert any("reset mail failed" in m for m in caplog.messages)
    for forbidden in (code, SMTP_PASSWORD, SECRET, "ada@example.com", NEW_PASSWORD):
        assert forbidden not in caplog.text, forbidden


def test_a_failed_mail_leaves_no_row(env: Callable[..., Env]) -> None:
    e = env()
    e.signup("ada@example.com")
    e.mailer.fail = True
    assert e.forgot("ada@example.com").status_code == 202
    assert e.rows() == []


# TC-18: reset attempts are limited per client address (AC-17)
def test_reset_attempts_are_limited_per_address_even_with_the_right_code(
    env: Callable[..., Env],
) -> None:
    e = env(auth_reset_max_tries_per_address=3)
    e.signup("ada@example.com")
    e.forgot("ada@example.com")
    code = e.mailer.code_for("ada@example.com")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(3):
        assert e.reset("ada@example.com", wrong).status_code == 400
    last = e.reset("ada@example.com", code)
    assert last.status_code == 429
    assert last.json()["detail"] == "too_many_reset_attempts"
    assert int(last.headers["retry-after"]) >= 1
    assert e.rows()[0][1] == 3  # the refused call checked no code
    other = e.reset("ada@example.com", code, address="10.0.0.2")
    assert other.status_code == 204


def test_malformed_input_does_not_use_up_the_attempt_budget(
    env: Callable[..., Env],
) -> None:
    e = env(auth_reset_max_tries_per_address=2)
    for _ in range(5):
        assert e.reset("bad", "123456").status_code == 422
        assert e.reset("a@example.com", "123456", password="x").status_code == 422
    assert e.reset("a@example.com", "123456").status_code == 400


def test_the_routes_are_in_the_openapi_document(env: Callable[..., Env]) -> None:
    paths = env().client().get("/openapi.json").json()["paths"]
    for path in (
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/options",
    ):
        assert path in paths


# ---- live server -------------------------------------------------------------------


@contextmanager
def _serve(app_env: Env) -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app_env.app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


# TC-1: the 202 arrives while the send is still blocked (AC-1)
def test_the_answer_arrives_before_the_mail_send_finishes(
    env: Callable[..., Env],
) -> None:
    e = env()
    e.signup("ada@example.com")
    e.mailer.gate = threading.Event()
    with _serve(e) as base:
        r = httpx.post(
            f"{base}/api/auth/forgot-password", json={"email": "ada@example.com"}
        )
        assert r.status_code == 202 and r.json() == GENERIC
        assert e.mailer.started.wait(10)  # the job is running ...
        assert not e.mailer.finished.is_set()  # ... and the answer did not wait for it
        assert e.mailer.sent == []
        e.mailer.gate.set()
        assert e.mailer.finished.wait(10)
    assert len(e.mailer.sent) == 1


# Measurement (tests.md): known vs unknown foreground latency; prints, asserts loosely
def test_known_and_unknown_emails_take_about_the_same_foreground_time(
    env: Callable[..., Env],
) -> None:
    e = env(auth_reset_max_per_email=0, auth_reset_max_per_address=0)
    e.signup("ada@example.com")
    e.mailer.delay = 0.05  # a slow send must not show in the foreground
    timings: dict[str, list[float]] = {"known": [], "unknown": []}
    with _serve(e) as base, httpx.Client() as c:
        for _ in range(200):
            for kind, email in (
                ("known", "ada@example.com"),
                ("unknown", "no@example.com"),
            ):
                t0 = time.perf_counter()
                assert (
                    c.post(
                        f"{base}/api/auth/forgot-password", json={"email": email}
                    ).status_code
                    == 202
                )
                timings[kind].append((time.perf_counter() - t0) * 1000)
    summary = {}
    for kind, values in timings.items():
        values.sort()
        summary[kind] = (statistics.median(values), values[int(len(values) * 0.95)])
    print(f"\nMEASURE forgot-password ms (median, p95): {summary}")
    assert abs(summary["known"][0] - summary["unknown"][0]) < 20
