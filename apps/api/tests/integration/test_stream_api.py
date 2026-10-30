"""TC-3 (stream), TC-5…TC-13, TC-20 (fallback): SSE streams over a live app (Docker)."""

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.agents_repo import SqlAgentsRepo
from newsdock_api.adapters.subscriptions_repo import SqlSubscriptionsRepo
from newsdock_api.config import Settings
from newsdock_api.domain.agents import ALL, make_key
from newsdock_api.domain.service import encode_cursor
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
CAP = 2


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
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    url = side_db[0]
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def base(engine: Engine) -> Iterator[str]:
    settings = Settings(
        auth_required=True, rate_limit_per_minute=0,
        sse_keepalive_seconds=1, sse_fallback_poll_seconds=1,
        sse_max_streams_per_agent=CAP,
    )  # fmt: skip
    with _serve(settings) as url:
        yield url


@pytest.fixture(scope="module")
def slow_fallback(engine: Engine) -> Iterator[str]:
    """Keep-alive 1 s but a 60 s fallback poll: deliveries must come from NOTIFY."""
    settings = Settings(
        auth_required=True, rate_limit_per_minute=0,
        sse_keepalive_seconds=1, sse_fallback_poll_seconds=60,
        sse_max_streams_per_agent=CAP,
    )  # fmt: skip
    with _serve(settings) as url:
        yield url


class Agent:
    def __init__(self, engine: Engine, name: str) -> None:
        self.repo = SqlAgentsRepo(engine)
        self.subs = SqlSubscriptionsRepo(engine)
        key = make_key()
        registered = self.repo.create_agent(name, key, None)
        self.id, self.key_id, self.raw = registered.id, registered.key_id, key.raw

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.raw}"}

    def subscribe(self, filter_json: dict[str, str]) -> str:
        return self.subs.create(self.id, filter_json).id


def add_article(engine: Engine, key: str, domain: str, themes: str = "{}") -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                    "domain, published_at, themes, persons, orgs) VALUES "
                    "(:k,'x','20261014120000','https://'||:d||'/'||:k,'title '||:k,:d,"
                    "now(),CAST(:t AS text[]),'{}','{}') RETURNING seq"
                ),
                {"k": key, "d": domain, "t": themes},
            ).scalar_one()
        )


def read(
    base: str, agent: Agent, sub: str, *, seconds: float, last_id: str | None = None,
    want: int | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:  # fmt: skip
    """Collect (events, raw non-empty lines) for up to `seconds` (or `want` events)."""
    headers = dict(agent.headers)
    if last_id:
        headers["Last-Event-ID"] = last_id
    events: list[dict[str, Any]] = []
    lines: list[str] = []
    deadline = time.time() + seconds
    current: dict[str, Any] = {}
    with httpx.stream(
        "GET", f"{base}/api/subscriptions/{sub}/stream", headers=headers,
        timeout=httpx.Timeout(10, read=5),
    ) as response:  # fmt: skip
        assert response.status_code == 200, response.status_code
        for line in response.iter_lines():
            if line:
                lines.append(line)
                key, _, value = line.partition(": ")
                if key == "id":
                    current["id"] = value
                elif key == "event":
                    current["event"] = value
                elif key == "data":
                    current["data"] = json.loads(value)
            elif current:
                events.append(current)
                current = {}
            if time.time() > deadline or (want and len(events) >= want):
                break
    return events, lines


def start_later(delay: float, fn: Any, *args: Any) -> threading.Thread:
    def go() -> None:
        time.sleep(delay)
        fn(*args)

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    return thread


# TC-5: no key / unknown / revoked
def test_stream_needs_a_valid_key(base: str, engine: Engine) -> None:
    owner = Agent(engine, "s-owner")
    sub = owner.subscribe({})
    url = f"{base}/api/subscriptions/{sub}/stream"
    assert httpx.get(url).status_code == 401
    assert httpx.get(url, headers={"Authorization": "Bearer junk"}).status_code == 401
    unknown = {"Authorization": f"Bearer {make_key().raw}"}
    assert httpx.get(url, headers=unknown).status_code == 401
    owner.repo.revoke_key(owner.id, owner.key_id, ALL)
    assert httpx.get(url, headers=owner.headers).status_code == 401


# TC-3 (stream part)
def test_other_agents_subscription_is_404(base: str, engine: Engine) -> None:
    alpha, beta = Agent(engine, "s-alpha"), Agent(engine, "s-beta")
    theirs = beta.subscribe({})
    response = httpx.get(
        f"{base}/api/subscriptions/{theirs}/stream", headers=alpha.headers
    )
    assert response.status_code == 404
    bad = httpx.get(
        f"{base}/api/subscriptions/not-a-uuid/stream", headers=alpha.headers
    )
    assert bad.status_code == 404


# TC-6 + TC-7: matching articles arrive (via NOTIFY), others do not
def test_matching_articles_are_pushed_and_others_are_not(
    slow_fallback: str, engine: Engine
) -> None:
    agent = Agent(engine, "s-push")
    sub = agent.subscribe({"domain": "push.example.com"})

    def inserts() -> None:
        add_article(engine, "p-other", "other.org")
        add_article(engine, "p-match", "push.example.com")

    start_later(1.0, inserts)
    t0 = time.time()
    events, _ = read(slow_fallback, agent, sub, seconds=8, want=1)
    assert [e["data"]["article_id"] for e in events] == ["p-match"]
    assert events[0]["event"] == "article"
    assert events[0]["data"]["domain"] == "push.example.com"
    assert "seq" not in events[0]["data"]  # never exposed raw
    with engine.connect() as conn:
        seq = conn.execute(
            text("SELECT seq FROM articles WHERE url_hash='p-match'")
        ).scalar_one()
    assert events[0]["id"] == encode_cursor(seq)
    assert time.time() - t0 < 6  # woken by NOTIFY, not the 60 s fallback poll


# TC-8: resume after a disconnect
def test_resume_with_last_event_id(base: str, engine: Engine) -> None:
    agent = Agent(engine, "s-resume")
    sub = agent.subscribe({"domain": "resume.example.com"})
    start_later(0.5, add_article, engine, "r-1", "resume.example.com")
    first, _ = read(base, agent, sub, seconds=6, want=1)
    assert [e["data"]["article_id"] for e in first] == ["r-1"]

    add_article(engine, "r-2", "resume.example.com")  # stored while disconnected
    add_article(engine, "r-skip", "elsewhere.org")
    add_article(engine, "r-3", "resume.example.com")
    again, _ = read(base, agent, sub, seconds=6, want=2, last_id=first[0]["id"])
    assert [e["data"]["article_id"] for e in again] == ["r-2", "r-3"]

    bad = httpx.get(
        f"{base}/api/subscriptions/{sub}/stream",
        headers={**agent.headers, "Last-Event-ID": "garbage!!"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "invalid_last_event_id"


# TC-9 + TC-10: default start position, and streaming never moves the cursor
def test_default_start_and_cursor_untouched(base: str, engine: Engine) -> None:
    with_cursor, without = Agent(engine, "s-cur"), Agent(engine, "s-nocur")
    before = add_article(engine, "c-before", "cur.example.com")
    with_cursor.repo.advance_cursor(with_cursor.id, before)
    add_article(engine, "c-after", "cur.example.com")
    sub_a = with_cursor.subscribe({"domain": "cur.example.com"})
    sub_b = without.subscribe({"domain": "cur.example.com"})

    a, _ = read(base, with_cursor, sub_a, seconds=4, want=1)
    assert [e["data"]["article_id"] for e in a] == ["c-after"]  # only after C
    b, _ = read(base, without, sub_b, seconds=4, want=2)
    assert [e["data"]["article_id"] for e in b] == ["c-before", "c-after"]  # window
    assert with_cursor.repo.get_cursor(with_cursor.id) == before  # TC-10
    assert without.repo.get_cursor(without.id) is None


# TC-12: keep-alive comments on an idle stream
def test_idle_streams_get_keepalive_pings(base: str, engine: Engine) -> None:
    agent = Agent(engine, "s-ping")
    sub = agent.subscribe({"domain": "silent.invalid"})
    _, lines = read(base, agent, sub, seconds=2.6)
    assert lines.count(": ping") >= 2


# TC-11: revocation / deletion end the stream; reconnect is refused
def test_revoking_the_key_ends_the_stream(base: str, engine: Engine) -> None:
    agent = Agent(engine, "s-revoke")
    sub = agent.subscribe({"domain": "silent.invalid"})
    start_later(1.0, agent.repo.revoke_key, agent.id, agent.key_id, ALL)
    t0 = time.time()
    with httpx.stream(
        "GET", f"{base}/api/subscriptions/{sub}/stream", headers=agent.headers,
        timeout=httpx.Timeout(10, read=8),
    ) as response:  # fmt: skip
        assert response.status_code == 200
        for _ in response.iter_lines():
            pass  # returns only when the server closes the stream
    assert time.time() - t0 < 6
    assert (
        httpx.get(
            f"{base}/api/subscriptions/{sub}/stream", headers=agent.headers
        ).status_code
        == 401
    )


def test_revocation_is_noticed_under_constant_traffic(
    slow_fallback: str, engine: Engine
) -> None:
    """Steady NOTIFY wake-ups must not starve the revoked-key re-check."""
    agent = Agent(engine, "s-busy")
    sub = agent.subscribe({"domain": "silent.invalid"})
    stop = threading.Event()

    def traffic() -> None:
        i = 0
        while not stop.is_set():
            add_article(engine, f"busy-{i}", "noise.example.com")
            i += 1
            time.sleep(0.2)

    noise = threading.Thread(target=traffic, daemon=True)
    noise.start()
    start_later(1.0, agent.repo.revoke_key, agent.id, agent.key_id, ALL)
    t0 = time.time()
    try:
        with httpx.stream(
            "GET", f"{slow_fallback}/api/subscriptions/{sub}/stream",
            headers=agent.headers, timeout=httpx.Timeout(10, read=8),
        ) as response:  # fmt: skip
            assert response.status_code == 200
            for _ in response.iter_lines():
                pass
        ended = time.time() - t0
    finally:
        stop.set()
        noise.join(timeout=5)
    assert ended < 5  # without the timer check this would run until traffic stops


def test_deleting_the_subscription_ends_the_stream(base: str, engine: Engine) -> None:
    agent = Agent(engine, "s-delete")
    sub = agent.subscribe({"domain": "silent.invalid"})
    start_later(1.0, agent.subs.delete_own, agent.id, sub)
    t0 = time.time()
    with httpx.stream(
        "GET", f"{base}/api/subscriptions/{sub}/stream", headers=agent.headers,
        timeout=httpx.Timeout(10, read=8),
    ) as response:  # fmt: skip
        assert response.status_code == 200
        for _ in response.iter_lines():
            pass
    assert time.time() - t0 < 6


# TC-13: concurrent stream cap, released on close
def test_stream_cap_per_agent(base: str, engine: Engine) -> None:
    alpha, beta = Agent(engine, "s-cap-a"), Agent(engine, "s-cap-b")
    sub_a, sub_b = alpha.subscribe({}), beta.subscribe({})
    url_a = f"{base}/api/subscriptions/{sub_a}/stream"
    with (
        httpx.stream("GET", url_a, headers=alpha.headers, timeout=10) as one,
        httpx.stream("GET", url_a, headers=alpha.headers, timeout=10) as two,
    ):
        assert (one.status_code, two.status_code) == (200, 200)
        third = httpx.get(url_a, headers=alpha.headers)
        assert third.status_code == 429 and "retry-after" in third.headers
        with httpx.stream(
            "GET", f"{base}/api/subscriptions/{sub_b}/stream", headers=beta.headers,
            timeout=10,
        ) as other:  # fmt: skip
            assert other.status_code == 200  # another agent is unaffected
    time.sleep(1.5)  # the server notices the disconnects and frees the slots
    with httpx.stream("GET", url_a, headers=alpha.headers, timeout=10) as again:
        assert again.status_code == 200


# TC-20 (fallback half): a lost listener connection does not stop delivery
def test_delivery_survives_a_killed_listener_connection(
    base: str, engine: Engine
) -> None:
    agent = Agent(engine, "s-kill")
    sub = agent.subscribe({"domain": "kill.example.com"})

    def kill_then_insert() -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE query ILIKE 'LISTEN articles_new%' "
                    "AND pid <> pg_backend_pid()"
                )
            )
        add_article(engine, "k-1", "kill.example.com")

    start_later(1.0, kill_then_insert)
    events, _ = read(base, agent, sub, seconds=8, want=1)
    assert [e["data"]["article_id"] for e in events] == ["k-1"]
