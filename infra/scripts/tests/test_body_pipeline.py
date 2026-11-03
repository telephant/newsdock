"""TC-24 (body-extraction AC-15): the rest of the platform does not depend on the
extractor.

Real code, no Kafka: the ingester cycle (fake GDELT source) -> processor `route()` ->
sink writers -> the API repo, on a throwaway Postgres from `side_postgres` (safe next
to a running dev stack), reusing the chain of `test_events_pipeline`. The extractor is
first not run at all, then run with a resolver that fails for every host (as if the web
were unreachable). In both cases ingestion, the sink, title search and `get_article`
behave as before, and the API's code path opens no network socket and imports no
fetcher.
"""

import ast
import asyncio
import socket
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_db.engine import make_engine
from newsdock_db.models import ArticleBody
from newsdock_db.testing import side_postgres
from newsdock_extractor.adapters.db import SqlBodyRepo
from newsdock_extractor.adapters.fetch import FetchConfig, Fetcher
from newsdock_extractor.adapters.resolve import ResolveError
from newsdock_extractor.adapters.wiring import worker_config
from newsdock_extractor.config import Settings as ExtractorSettings
from newsdock_extractor.domain.loop import ExtractWorker
from newsdock_extractor.domain.picking import QueueRow
from newsdock_extractor.domain.schedule import HostScheduler
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from .test_events_pipeline import Chain, Data

ROOT = Path(__file__).resolve().parents[3]
# what the API must never import: anything that fetches or parses article pages
FORBIDDEN_IN_API = {"newsdock_extractor", "trafilatura", "protego", "lxml", "bs4"}


@pytest.fixture(scope="module")
def side_db() -> Iterator[tuple[str, str]]:
    """A throwaway Postgres; the dev-stack guard looks for the name `side_db`."""
    mp = pytest.MonkeyPatch()
    with side_postgres("newsdock-side-body-pipeline") as (url, dsn):
        mp.setenv("DATABASE_URL", url)
        try:
            yield url, dsn
        finally:
            mp.undo()


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE events, mentions"))
    yield eng
    eng.dispose()


class DeadWebResolver:
    """Every host fails to resolve: the extractor can fetch nothing."""

    async def resolve(self, host: str) -> list[str]:
        raise ResolveError(host)


def failing_extractor(engine: Engine) -> ExtractWorker:
    settings = ExtractorSettings()
    scheduler: HostScheduler[QueueRow] = HostScheduler(
        clock=time.monotonic,
        per_host_delay=settings.per_host_delay_seconds,
        max_crawl_delay=settings.max_crawl_delay_seconds,
    )
    return ExtractWorker(
        SqlBodyRepo(engine),
        Fetcher(
            FetchConfig.from_settings(settings),
            resolver=DeadWebResolver(),
            clock=lambda: datetime.now(UTC),
        ),
        scheduler,
        worker_config(settings),
        clock=lambda: datetime.now(UTC),
    )


def search(repo: SqlArticleRepo) -> dict[str, Any]:
    found = repo.search(
        time_from=None, time_to=None, theme=None, domain=None, text=None, limit=50
    )
    return {a.article_id: a for a in found}


def body_rows(engine: Engine) -> list[tuple[str, str | None]]:
    with Session(engine) as session:
        rows = session.execute(select(ArticleBody.status, ArticleBody.text)).all()
    return [(r[0], r[1]) for r in rows]


def count_articles(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM articles")).scalar_one())


@pytest.mark.docker
def test_serving_and_ingestion_do_not_need_the_extractor(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = Data()
    chain = Chain(engine, data)
    first = chain.cycle()
    assert first, "the chain published nothing"
    stored = count_articles(engine)
    assert stored > 0

    # --- the extractor is not running at all (stopped) -------------------------------
    repo = SqlArticleRepo(engine)
    titles = search(repo)
    assert data.article_id in titles
    detail = repo.get(data.article_id)
    assert detail is not None
    assert (detail.body, detail.body_status) == (None, "none")
    assert body_rows(engine) == []

    # --- the extractor runs but every fetch fails ------------------------------------
    worker = failing_extractor(engine)
    for _ in range(3):
        if asyncio.run(worker.run_pass()).processed == 0:
            break
    rows = body_rows(engine)
    assert rows, "the extractor never queued anything"
    assert all(status != "ok" and text_ is None for status, text_ in rows)

    # slots keep arriving: replaying them changes nothing and breaks nothing
    chain.write(first)
    assert count_articles(engine) == stored
    assert set(search(repo)) == set(titles)
    again = repo.get(data.article_id)
    assert again is not None
    assert again.body is None and again.body_status != "ok"
    assert again.title == detail.title and again.events == detail.events

    # --- the API's read path opens no network socket ---------------------------------
    connects: list[object] = []
    real_connect = socket.socket.connect

    def spy(self: socket.socket, address: Any) -> None:
        connects.append(address)
        real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", spy)
    fresh = SqlArticleRepo(
        make_engine(engine.url.render_as_string(hide_password=False))
    )
    assert data.article_id in search(fresh)
    assert fresh.get(data.article_id) is not None
    assert (
        fresh.search(
            time_from=None,
            time_to=None,
            theme=None,
            domain=None,
            text=None,
            limit=5,
            include=("body", "events"),
        )  # fmt: skip
        is not None
    )
    assert connects == [], f"the API read path opened sockets: {connects}"


def test_the_api_package_imports_no_fetcher_or_parser() -> None:
    offenders: list[str] = []
    for path in (ROOT / "apps" / "api" / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in FORBIDDEN_IN_API:
                    offenders.append(f"{path.relative_to(ROOT)}: {name}")
    assert offenders == []
