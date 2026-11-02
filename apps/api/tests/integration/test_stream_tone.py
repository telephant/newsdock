"""TC-16 (AC-12): a subscription with `min_negativity` delivers only strongly negative
articles, with an event payload that has no tone keys (Docker, live app)."""

import json
import socket
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
from newsdock_api.adapters.subscriptions_repo import SqlSubscriptionsRepo
from newsdock_api.config import Settings
from newsdock_api.domain.agents import make_key
from newsdock_api.domain.subscriptions import parse_filter
from newsdock_db.engine import make_engine
from sqlalchemy import Engine, text

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]


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
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def base(engine: Engine) -> Iterator[str]:
    settings = Settings(
        auth_required=True, rate_limit_per_minute=0,
        sse_keepalive_seconds=1, sse_fallback_poll_seconds=1,
    )  # fmt: skip
    with _serve(settings) as url:
        yield url


def add_article(engine: Engine, key: str, tone_neg: float | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO articles (url_hash, gkg_record_id, slot, url, title, "
                "domain, published_at, themes, persons, orgs, tone, tone_neg) VALUES "
                "(:k,'x','20261030120000','https://e.com/'||:k,'title '||:k,'e.com',"
                "now(),'{}','{}','{}',:tn,:tn)"
            ),
            {"k": key, "tn": tone_neg},
        )


def read(base: str, key: str, sub: str, *, want: int, seconds: float) -> list[Any]:
    events: list[Any] = []
    current: dict[str, Any] = {}
    deadline = time.time() + seconds
    with httpx.stream(
        "GET", f"{base}/api/subscriptions/{sub}/stream",
        headers={"Authorization": f"Bearer {key}"},
        timeout=httpx.Timeout(10, read=5),
    ) as response:  # fmt: skip
        assert response.status_code == 200, response.status_code
        for line in response.iter_lines():
            if line:
                name, _, value = line.partition(": ")
                if name == "data":
                    current["data"] = json.loads(value)
                elif name == "id":
                    current["id"] = value
            elif current:
                events.append(current)
                current = {}
            if time.time() > deadline or len(events) >= want:
                break
    return events


def test_only_strongly_negative_articles_are_delivered(
    base: str, engine: Engine
) -> None:
    key = make_key()
    registered = SqlAgentsRepo(engine).create_agent("s-tone", key, None)
    stored = parse_filter({"min_negativity": 8}, 200).as_json()
    sub = SqlSubscriptionsRepo(engine).create(registered.id, stored)

    def inserts() -> None:
        time.sleep(1.0)
        add_article(engine, "calm", 3.0)
        add_article(engine, "no-tone", None)
        add_article(engine, "grim", 12.5)

    thread = threading.Thread(target=inserts, daemon=True)
    thread.start()
    events = read(base, key.raw, sub.id, want=1, seconds=10)
    thread.join()
    assert [e["data"]["article_id"] for e in events] == ["grim"]
    payload = events[0]["data"]
    assert not {"tone", "tone_pos", "tone_neg", "tone_polarity"} & set(payload)
    assert "seq" not in payload


def test_the_stored_filter_round_trips_through_postgres(
    base: str, engine: Engine
) -> None:
    key = make_key()
    registered = SqlAgentsRepo(engine).create_agent("s-tone-rt", key, None)
    repo = SqlSubscriptionsRepo(engine)
    created = repo.create(registered.id, {"theme": "ECON_*", "min_negativity": 8.5})
    (listed,) = repo.list_own(registered.id)
    assert listed.id == created.id
    assert listed.filter == {"theme": "ECON_*", "min_negativity": 8.5}
