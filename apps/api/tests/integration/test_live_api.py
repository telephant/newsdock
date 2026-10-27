"""TC-36 (AC-15) and M-c: the live feed for logged-in users (Docker, live uvicorn)."""

import json
import socket
import statistics
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_api.domain.service import encode_cursor
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-login-test"
PASSWORD = "correct-horse-battery"
CAP = 2
KEEPALIVE = 1


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@contextmanager
def _serve(settings: Settings) -> Iterator[str]:
    from newsdock_api.adapters.http import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings), host="127.0.0.1", port=port, log_level="warning"
        )
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
    time.sleep(0.5)  # let the NOTIFY listener connect
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


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


@pytest.fixture(scope="module")
def base(engine: Engine) -> Iterator[str]:
    """NOTIFY must do the work: the fallback poll is far longer than any test."""
    settings = Settings(
        auth_required=True, rate_limit_per_minute=0,
        sse_keepalive_seconds=KEEPALIVE, sse_fallback_poll_seconds=60,
        live_max_streams_per_user=CAP,
    )  # fmt: skip
    with _serve(settings) as url:
        yield url


@pytest.fixture(scope="module")
def open_base(engine: Engine) -> Iterator[str]:
    settings = Settings(
        auth_required=False, rate_limit_per_minute=0,
        sse_keepalive_seconds=KEEPALIVE, sse_fallback_poll_seconds=60,
    )  # fmt: skip
    with _serve(settings) as url:
        yield url


@pytest.fixture()
def clean(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        conn.execute(text("TRUNCATE agents CASCADE"))
    return engine


def add_article(engine: Engine, key: str, domain: str = "example.com") -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                    "domain, published_at, themes, persons, orgs) VALUES "
                    "(:k,'x','20261027120000','https://'||:d||'/'||:k,'title '||:k,:d,"
                    "now(),'{}','{}','{}') RETURNING seq"
                ),
                {"k": key, "d": domain},
            ).scalar_one()
        )


def join(base: str, email: str) -> dict[str, str]:
    """Sign up (the first account is the owner) and log in; the cookie as a header."""
    body = {"email": email, "password": PASSWORD}
    httpx.post(f"{base}/api/auth/signup", json=body)
    response = httpx.post(f"{base}/api/auth/login", json=body)
    assert response.status_code == 200, response.text
    token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    return {"cookie": f"newsdock_session={token}"}


class Live:
    """One /api/live connection read by a thread; events are (received_at, dict)."""

    def __init__(
        self,
        base: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> None:
        self.events: list[tuple[float, dict[str, Any]]] = []
        self.status: int | None = None
        self.headers_seen: httpx.Headers | None = None
        self.opened = threading.Event()
        self.done = threading.Event()
        self._stop = threading.Event()
        self._args = (f"{base}/api/live", headers or {}, params or {})
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self.opened.wait(10), "no response from /api/live"

    def _run(self) -> None:
        url, headers, params = self._args
        try:
            with httpx.stream(
                "GET", url, headers=headers, params=params,
                timeout=httpx.Timeout(10, read=6),
            ) as response:  # fmt: skip
                self.status = response.status_code
                self.headers_seen = response.headers
                self.opened.set()
                if response.status_code != 200:
                    return
                current: dict[str, Any] = {}
                for line in response.iter_lines():
                    if self._stop.is_set():
                        break
                    if line:
                        key, _, value = line.partition(": ")
                        if key == "id":
                            current["id"] = value
                        elif key == "event":
                            current["event"] = value
                        elif key == "data":
                            current["data"] = json.loads(value)
                    elif current:
                        self.events.append((time.time(), current))
                        current = {}
        except httpx.HTTPError:
            pass
        finally:
            self.opened.set()
            self.done.set()

    def wait_events(self, n: int, timeout: float = 6.0) -> list[dict[str, Any]]:
        deadline = time.time() + timeout
        while len(self.events) < n and time.time() < deadline:
            time.sleep(0.05)
        return [e for _, e in self.events]

    def close(self) -> None:
        self._stop.set()
        self.done.wait(KEEPALIVE * 3 + 2)


# ---- access ---------------------------------------------------------------------
def test_anonymous_and_non_user_callers_are_refused(base: str, clean: Engine) -> None:
    join(base, "owner@x.io")
    key = make_key()
    SqlAgentsRepo(clean).create_agent("alpha", key)
    assert Live(base).status == 401
    assert Live(base, {"cookie": "newsdock_session=forged"}).status == 401
    assert Live(base, {"authorization": f"Bearer {key.raw}"}).status == 403


@pytest.mark.parametrize("role", ["owner", "admin", "viewer"])
def test_every_role_may_open_the_feed(base: str, clean: Engine, role: str) -> None:
    join(base, "owner@x.io")  # the first account is the owner
    headers = join(base, f"{role}@x.io")
    if role != "viewer":
        with clean.begin() as conn:
            conn.execute(
                text("UPDATE users SET role = :r WHERE email = :e"),
                {"r": role, "e": f"{role}@x.io"},
            )
    live = Live(base, headers)
    assert live.status == 200
    assert live.headers_seen is not None
    assert live.headers_seen["content-type"].startswith("text/event-stream")
    live.close()


def test_a_listed_origin_may_read_the_stream_with_credentials(
    base: str, clean: Engine
) -> None:
    headers = {**join(base, "owner@x.io"), "origin": "http://localhost:3000"}
    live = Live(base, headers)
    assert live.headers_seen is not None
    assert live.headers_seen["access-control-allow-origin"] == "http://localhost:3000"
    assert live.headers_seen["access-control-allow-credentials"] == "true"
    live.close()


# ---- delivery -------------------------------------------------------------------
def test_no_backlog_then_a_new_article_arrives_with_a_cursor_id(
    base: str, clean: Engine
) -> None:
    for i in range(3):
        add_article(clean, f"old-{i}")  # rows that exist before connecting
    live = Live(base, join(base, "owner@x.io"))
    assert live.status == 200
    time.sleep(KEEPALIVE * 2.5)
    assert live.events == [], "history is the feed page's job, not the stream's"
    seq = add_article(clean, "fresh-1")
    events = live.wait_events(1)
    live.close()
    assert len(events) == 1
    assert events[0]["event"] == "article"
    assert events[0]["id"] == encode_cursor(seq)
    assert events[0]["data"]["title"] == "title fresh-1"


def test_reconnecting_with_last_event_id_returns_exactly_the_missed_rows(
    base: str, clean: Engine
) -> None:
    headers = join(base, "owner@x.io")
    first = Live(base, headers)
    add_article(clean, "r-1")
    seen = first.wait_events(1)
    first.close()
    last = seen[-1]["id"]
    s2, s3 = add_article(clean, "r-2"), add_article(clean, "r-3")
    again = Live(base, {**headers, "Last-Event-ID": last})
    events = again.wait_events(2)
    again.close()
    assert [e["id"] for e in events] == [encode_cursor(s2), encode_cursor(s3)]


def test_a_malformed_last_event_id_is_a_400(base: str, clean: Engine) -> None:
    headers = join(base, "owner@x.io")
    assert Live(base, {**headers, "Last-Event-ID": "not-a-cursor"}).status == 400


def test_the_optional_filter_passes_only_matching_rows(
    base: str, clean: Engine
) -> None:
    live = Live(base, join(base, "owner@x.io"), {"domain": "only.org"})
    assert live.status == 200
    add_article(clean, "skip-1", "other.net")
    seq = add_article(clean, "keep-1", "only.org")
    events = live.wait_events(1)
    time.sleep(0.5)
    live.close()
    assert [e["id"] for e in live.wait_events(1, 0.1)] == [encode_cursor(seq)]
    assert len(events) == 1 and events[0]["data"]["domain"] == "only.org"


def test_a_bad_filter_is_a_422(base: str, clean: Engine) -> None:
    headers = join(base, "owner@x.io")
    assert Live(base, headers, {"theme": "EC*ON"}).status == 422  # star only at the end
    assert Live(base, headers, {"domain": "x" * 500}).status == 422


# ---- limits and lifetime ----------------------------------------------------------
def test_one_user_cannot_open_more_than_the_cap(base: str, clean: Engine) -> None:
    headers = join(base, "owner@x.io")
    other = join(base, "other@x.io")
    held = [Live(base, headers) for _ in range(CAP)]
    assert all(h.status == 200 for h in held)
    refused = Live(base, headers)
    assert refused.status == 429
    assert refused.headers_seen is not None and "retry-after" in refused.headers_seen
    other_ok = Live(base, other)  # the cap is per user
    assert other_ok.status == 200
    held[0].close()
    time.sleep(KEEPALIVE * 2)
    reopened = Live(base, headers)
    assert reopened.status == 200
    for live in (*held, other_ok, reopened):
        live.close()


def test_logout_ends_an_open_stream_within_two_keepalives(
    base: str, clean: Engine
) -> None:
    headers = join(base, "owner@x.io")
    live = Live(base, headers)
    assert live.status == 200
    out = httpx.post(f"{base}/api/auth/logout", headers=headers)
    assert out.status_code == 204
    assert live.done.wait(KEEPALIVE * 2 + 2), "the stream outlived its session"


def test_deleting_the_user_ends_their_stream(base: str, clean: Engine) -> None:
    owner = join(base, "owner@x.io")
    victim = join(base, "victim@x.io")
    live = Live(base, victim)
    assert live.status == 200
    with clean.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = 'victim@x.io'"))
    assert live.done.wait(KEEPALIVE * 2 + 2)
    assert httpx.get(f"{base}/api/auth/me", headers=owner).status_code == 200


def test_in_dev_mode_the_feed_is_open_to_anonymous_callers(
    open_base: str, clean: Engine
) -> None:
    live = Live(open_base)
    assert live.status == 200
    seq = add_article(clean, "dev-1")
    events = live.wait_events(1)
    live.close()
    assert [e["id"] for e in events] == [encode_cursor(seq)]


# ---- M-c -------------------------------------------------------------------------
def test_measure_insert_to_event_latency(base: str, clean: Engine) -> None:
    live = Live(base, join(base, "owner@x.io"))
    latencies: list[float] = []
    for i in range(20):
        committed = time.time()
        add_article(clean, f"lat-{i}")
        live.wait_events(i + 1)
        latencies.append(live.events[i][0] - committed)
        time.sleep(0.2)
    live.close()
    median, worst = statistics.median(latencies), max(latencies)
    print(
        f"M-c insert->event latency, 20 samples: median {median:.3f}s max {worst:.3f}s"
    )
    assert len(latencies) == 20
    assert worst < KEEPALIVE * 2  # the wake-up (NOTIFY) path, not the 60 s fallback
