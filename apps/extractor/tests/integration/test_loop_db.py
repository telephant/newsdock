"""TC-2, TC-13, TC-15 end to end: the real repo and fetcher and a local web server.

Hostnames such as `ok.test` all resolve to the local server (a fake resolver); the
address policy names its port and allows loopback, which no setting can do in
production. Runs on a throwaway Postgres (`side_db`); no real site is contacted.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_db.engine import make_engine
from newsdock_db.models import Article, ArticleBody, ArticlePassage
from newsdock_db.testing import article
from newsdock_extractor.adapters.db import SqlBodyRepo
from newsdock_extractor.adapters.fetch import FetchConfig, Fetcher
from newsdock_extractor.adapters.resolve import AddressPolicy, ResolveError
from newsdock_extractor.domain.loop import ExtractWorker, WorkerConfig
from newsdock_extractor.domain.picking import QueueRow
from newsdock_extractor.domain.schedule import HostScheduler
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "apps" / "extractor" / "tests" / "fixtures"
NEWS = (FIXTURES / "news_page.html").read_bytes()
STUB = (FIXTURES / "stub_page.html").read_bytes()
NOW = datetime.now(UTC) + timedelta(minutes=10)  # see test_repo.py
UA = "newsdock-extractor/0.1 (test; respects robots.txt)"
ROBOTS = b"User-agent: *\nDisallow: /blocked\n"


class Resolver:
    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table

    async def resolve(self, host: str) -> list[str]:
        if host not in self.table:
            raise ResolveError(host)
        return self.table[host]


class Clock:
    def __init__(self) -> None:
        self.seconds = 1_000.0

    def __call__(self) -> float:
        return self.seconds


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


@pytest.fixture()
def clean(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    return engine


def add(engine: Engine, key: str, url: str, *, age_hours: float = 1.0) -> None:
    row = article(key, f"title {key}", domain=f"{key}.test")
    row.url = url
    row.ingested_at = NOW - timedelta(hours=age_hours)
    with Session(engine) as session:
        session.add(row)
        session.commit()


def build(engine: Engine, site: Any, clock: Clock) -> ExtractWorker:
    hosts = {
        f"{name}.test": ["127.0.0.1"]
        for name in ("ok", "blocked", "gone", "pdf", "stub", "boom", "twin")
    }
    hosts["internal.test"] = ["10.0.0.1"]
    fetcher = Fetcher(
        FetchConfig(
            user_agent=UA,
            connect_timeout_seconds=2.0,
            read_timeout_seconds=1.0,
            total_timeout_seconds=4.0,
            max_bytes=100_000,
            max_redirects=3,
            max_crawl_delay_seconds=30.0,
            robots_ttl_hours=24,
            robots_failure_minutes=60,
        ),
        resolver=Resolver(hosts),
        policy=AddressPolicy(allow_loopback=True, allowed_ports=(site.port,)),
        clock=lambda: NOW,
    )
    scheduler: HostScheduler[QueueRow] = HostScheduler(
        clock=clock, per_host_delay=5.0, max_crawl_delay=30.0
    )
    config = WorkerConfig(
        batch_size=200,
        concurrency=16,
        retention_days=7,
        backfill_hours=6,
        min_chars=200,
        text_cap_chars=20_000,
        passage_chars=1000,
        passage_max_chars=1200,
        max_attempts=3,
        retry_backoff_minutes=(5, 30),
        max_crawl_delay_seconds=30.0,
        robots_failure_minutes=60,
    )
    return ExtractWorker(
        SqlBodyRepo(engine), fetcher, scheduler, config, clock=lambda: NOW
    )


def passes(worker: ExtractWorker) -> int:
    """Run passes until nothing is processed any more; returns the rows processed."""
    total = 0
    for _ in range(10):
        done = asyncio.run(worker.run_pass()).processed
        total += done
        if done == 0:
            break
    return total


def bodies(engine: Engine) -> dict[str, ArticleBody]:
    with Session(engine) as session:
        rows = session.scalars(select(ArticleBody)).all()
        session.expunge_all()
    return {r.url_hash: r for r in rows}


def serve(site: Any) -> None:
    site.route("/robots.txt", body=ROBOTS, content_type="text/plain")
    site.route("/ok", body=NEWS)
    site.route("/blocked", body=NEWS)
    site.route("/gone", status=404, body=b"gone")
    site.route("/pdf", body=b"%PDF-1.7", content_type="application/pdf")
    site.route("/stub", body=STUB)
    site.route("/boom", status=500, body=b"error")


def url(site: Any, host: str, path: str) -> str:
    return f"http://{host}.test:{site.port}{path}"


def test_every_kind_of_page_ends_with_its_status_in_the_database(
    clean: Engine, site: Any
) -> None:
    serve(site)
    cases = {
        "ok": ("ok", "/ok"),
        "blocked": ("blocked", "/blocked"),
        "gone": ("gone", "/gone"),
        "pdf": ("pdf", "/pdf"),
        "stub": ("stub", "/stub"),
        "boom": ("boom", "/boom"),
    }
    for key, (host, path) in cases.items():
        add(clean, key, url(site, host, path))
    add(clean, "internal", f"http://internal.test:{site.port}/x")
    worker = build(clean, site, Clock())

    assert passes(worker) == 7
    found = bodies(clean)
    got = {k: (b.status, b.http_status, b.attempts) for k, b in found.items()}
    assert got == {
        "ok": ("ok", 200, 1),
        "blocked": ("blocked_robots", None, 1),  # robots.txt said no
        "gone": ("http_error", 404, 1),
        "pdf": ("not_html", 200, 1),
        "stub": ("no_text", 200, 1),
        "boom": ("pending", 500, 1),  # a retry is waiting
        "internal": ("blocked_address", None, 1),  # a private address
    }
    assert found["ok"].text and "Governor Alex Sample" in found["ok"].text
    assert all(found[k].text is None for k in found if k != "ok")
    assert found["boom"].next_attempt_at == NOW + timedelta(minutes=5)
    assert site.hits("/blocked") == []  # never requested
    with Session(clean) as session:
        passages = session.scalars(
            select(ArticlePassage).order_by(ArticlePassage.idx)
        ).all()
    assert passages and {p.url_hash for p in passages} == {"ok"}
    assert [p.idx for p in passages] == list(range(len(passages)))
    assert all(p.embedding is None for p in passages)


def test_nothing_is_fetched_twice(clean: Engine, site: Any) -> None:
    serve(site)
    for key, path in (("ok", "/ok"), ("gone", "/gone"), ("boom", "/boom")):
        add(clean, key, url(site, key, path))
    worker = build(clean, site, Clock())
    assert passes(worker) == 3
    first = {p: len(site.hits(p)) for p in ("/ok", "/gone", "/boom")}
    assert first == {"/ok": 1, "/gone": 1, "/boom": 1}
    assert passes(worker) == 0  # the failed one waits five minutes
    again = build(clean, site, Clock())  # a restart: the queue lives in the database
    assert passes(again) == 0
    assert {p: len(site.hits(p)) for p in ("/ok", "/gone", "/boom")} == first
    with Session(clean) as session:
        assert session.scalar(text("SELECT count(*) FROM article_bodies")) == 3


def test_a_retry_is_taken_again_when_it_is_due(clean: Engine, site: Any) -> None:
    serve(site)
    add(clean, "boom", url(site, "boom", "/boom"))
    clock = Clock()
    worker = build(clean, site, clock)
    assert passes(worker) == 1
    with Session(clean) as session:  # the retry wait is over...
        session.execute(
            text("UPDATE article_bodies SET next_attempt_at = :t"),
            {"t": NOW - timedelta(seconds=1)},
        )
        session.commit()
    assert passes(worker) == 0  # ...but the site is still resting from the last request
    clock.seconds += 5.1
    assert passes(worker) == 1
    row = bodies(clean)["boom"]
    assert (row.status, row.attempts) == ("pending", 2)
    assert len(site.hits("/boom")) == 2


def test_one_site_is_asked_one_page_at_a_time(clean: Engine, site: Any) -> None:
    serve(site)
    site.route("/one", body=NEWS)
    site.route("/two", body=NEWS)
    add(clean, "twin", url(site, "twin", "/one"), age_hours=2)
    add(clean, "twin2", url(site, "twin", "/two"), age_hours=1)
    clock = Clock()
    worker = build(clean, site, clock)
    assert asyncio.run(worker.run_pass()).processed == 1
    assert [len(site.hits(p)) for p in ("/one", "/two")] == [0, 1]  # the newest first
    assert asyncio.run(worker.run_pass()).processed == 0  # the site is waiting
    clock.seconds += 5.1
    assert asyncio.run(worker.run_pass()).processed == 1
    assert [len(site.hits(p)) for p in ("/one", "/two")] == [1, 1]


def test_articles_that_arrive_later_are_picked_up_by_the_next_pass(
    clean: Engine, site: Any
) -> None:
    serve(site)
    worker = build(clean, site, Clock())
    assert passes(worker) == 0
    add(clean, "ok", url(site, "ok", "/ok"))
    assert passes(worker) == 1
    assert bodies(clean)["ok"].status == "ok"


def test_retention_removes_the_text_and_the_passages_with_the_article(
    clean: Engine, site: Any
) -> None:
    serve(site)
    add(clean, "ok", url(site, "ok", "/ok"))
    worker = build(clean, site, Clock())
    assert passes(worker) == 1
    with Session(clean) as session:
        assert session.scalar(text("SELECT count(*) FROM article_passages")) >= 1
        # the sink's retention statement, a week later
        session.execute(
            delete(Article).where(Article.ingested_at < NOW + timedelta(days=7))
        )
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM article_bodies")) == 0
        assert session.scalar(text("SELECT count(*) FROM article_passages")) == 0
