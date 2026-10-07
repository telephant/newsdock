"""M2a TC-9: a 3-copy story yields exactly one agent analysis (Docker).

Lives in infra/scripts/tests because it crosses apps (agent loop → api → db),
which app-local tests must not do (DR-7).
"""

import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from newsdock_agent.adapters.mcp import McpApiClient
from newsdock_agent.domain.loop import AgentLoop
from newsdock_agent.domain.score import Score
from newsdock_db.engine import make_engine
from newsdock_db.models import Analysis, Article, ArticleSource
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "newsdock-storyagent-test"
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
CANONICAL = "canon-econ"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


class FakeScorer:
    def score(self, title: str) -> Score | None:
        return Score(relevant=True, score=0.9, reason="fake")


class MemCursor:
    def __init__(self) -> None:
        self.value: str | None = None

    def load(self) -> str | None:
        return self.value

    def save(self, cursor: str) -> None:
        self.value = cursor


@pytest.fixture(scope="module")
def stack() -> Iterator[tuple[str, str]]:
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

    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(engine) as session:
        session.add(Article(
            url_hash=CANONICAL, gkg_record_id="x", slot="20261005120000",
            url="https://a.example/econ", title="central bank raises rates",
            domain="a.example", published_at=NOW, themes=["ECON_RATES"],
            persons=[], orgs=[], story_key="central bank raises rates",
        ))  # fmt: skip
        session.commit()
        for i, hours in enumerate((0.0, 1.0, 2.0)):
            session.add(ArticleSource(
                url_hash=f"copy-{i}", article_id=CANONICAL,
                url=f"https://s{i}.example/econ", domain=f"s{i}.example",
                slot="20261005120000", gkg_record_id="x",
                published_at=NOW + timedelta(hours=hours),
            ))  # fmt: skip
        session.commit()
    engine.dispose()

    from newsdock_api.adapters.http import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
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
    yield f"http://127.0.0.1:{port}", url
    server.should_exit = True
    thread.join(timeout=10)
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


def test_three_copies_yield_one_analysis(stack: tuple[str, str]) -> None:
    base_url, db_url = stack
    loop = AgentLoop(
        McpApiClient(f"{base_url}/mcp"),
        FakeScorer(),
        MemCursor(),
        agent_name="demo-financial",
        theme_prefixes=("ECON_",),
    )
    submitted = loop.run_once()
    assert submitted == 1  # the story appears once, so it is scored once

    engine = make_engine(db_url)
    with Session(engine) as session:
        analyses = session.execute(
            select(Analysis.article_id, Analysis.agent_name)
        ).all()
    engine.dispose()
    assert analyses == [(CANONICAL, "demo-financial")]
