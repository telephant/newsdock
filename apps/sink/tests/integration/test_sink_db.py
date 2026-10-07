"""M2a TC-2…TC-5, TC-12 + M1 cross-slot/retention against real Postgres (Docker)."""

import hashlib
import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_core.contracts import CleanArticle
from newsdock_db.engine import make_engine
from newsdock_db.models import Article, ArticleSource
from newsdock_sink.adapters.db import SqlArticleWriter
from newsdock_sink.domain.retention import cutoff
from newsdock_sink.domain.writer import SinkItem, process_batch
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
PROJECT = "newsdock-sink-test"
SLOT = "20261004081500"
BASE = "http://x"


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.fixture(scope="module")
def engine_url(request: pytest.FixtureRequest) -> Iterator[str]:
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
    mp.undo()
    yield url
    _compose("down", "-v", "--remove-orphans")


@pytest.fixture()
def clean_db(engine_url: str) -> Iterator[str]:
    engine = make_engine(engine_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
        conn.execute(text("TRUNCATE ingest_slot"))
    engine.dispose()
    yield engine_url


class NullDlq:
    def send(self, key: str, message: object) -> None:
        raise AssertionError(f"unexpected dlq message for {key}")


def _count(url: str) -> int:
    engine = make_engine(url)
    with Session(engine) as session:
        n = session.scalar(select(func.count()).select_from(Article))
    engine.dispose()
    return int(n or 0)


def _fixture_article() -> CleanArticle:
    with (FIXTURES / "expected_articles.json").open() as f:
        return CleanArticle.model_validate(json.load(f)[0])


def _copy(base: CleanArticle, *, url: str, slot: str | None = None,
          hours: float = 0.0, title: str | None = None) -> CleanArticle:  # fmt: skip
    return base.model_copy(update={
        "url": url,
        "url_hash": hashlib.sha256(url.encode()).hexdigest(),
        "slot": slot or base.slot,
        "title": title if title is not None else base.title,
        "published_at": base.published_at + timedelta(hours=hours),
    })  # fmt: skip


def _items(*articles: CleanArticle) -> list[SinkItem]:
    return [
        SinkItem(key=a.url_hash, value=a.model_dump_json().encode()) for a in articles
    ]


def _source_rows(url: str) -> list[tuple[str, str]]:
    engine = make_engine(url)
    with Session(engine) as session:
        rows = session.execute(
            select(ArticleSource.url_hash, ArticleSource.article_id)
        ).all()
    engine.dispose()
    return [(r[0], r[1]) for r in rows]


# M1 TC-12: the same URL in two different slots stores one article
def test_cross_slot_dedup_same_url(clean_db: str) -> None:
    article = _fixture_article()
    other_slot = article.model_copy(update={"slot": "20261004083000"})
    writer = SqlArticleWriter(make_engine(clean_db))
    result = process_batch(_items(article, other_slot), writer, NullDlq())
    assert result.canonicals == 1 and result.url_duplicates == 1
    assert _count(clean_db) == 1


# M2a TC-2: two copies of one story → 1 canonical + 2 sources
def test_two_copies_one_canonical_two_sources(clean_db: str) -> None:
    base = _fixture_article()
    copy = _copy(base, url="https://other.example/same-story", hours=1)
    writer = SqlArticleWriter(make_engine(clean_db))
    result = process_batch(_items(base, copy), writer, NullDlq())
    assert result.canonicals == 1 and result.grouped == 1
    assert _count(clean_db) == 1
    sources = _source_rows(clean_db)
    assert len(sources) == 2
    assert {cid for _, cid in sources} == {base.url_hash}


# M2a TC-3: a later-slot copy adds a source, not an article
def test_cross_slot_copy_adds_source(clean_db: str) -> None:
    base = _fixture_article()
    writer = SqlArticleWriter(make_engine(clean_db))
    process_batch(_items(base), writer, NullDlq())
    late = _copy(base, url="https://late.example/copy",
                 slot="20261004100000", hours=3)  # fmt: skip
    result = process_batch(_items(late), writer, NullDlq())
    assert result.canonicals == 0 and result.grouped == 1
    assert _count(clean_db) == 1 and len(_source_rows(clean_db)) == 2


# M2a TC-4: redelivering stored URLs adds nothing anywhere
def test_redelivery_adds_no_rows(clean_db: str) -> None:
    base = _fixture_article()
    copy = _copy(base, url="https://other.example/x", hours=1)
    writer = SqlArticleWriter(make_engine(clean_db))
    process_batch(_items(base, copy), writer, NullDlq())
    result = process_batch(_items(base, copy), writer, NullDlq())
    assert result.canonicals == 0 and result.grouped == 0
    assert result.url_duplicates == 2
    assert _count(clean_db) == 1 and len(_source_rows(clean_db)) == 2


# M2a TC-5: same key outside the 48 h window → two separate canonicals
def test_window_guard_creates_second_canonical(clean_db: str) -> None:
    base = _fixture_article()
    far = _copy(base, url="https://muchlater.example/x", hours=72)
    writer = SqlArticleWriter(make_engine(clean_db))
    result = process_batch(_items(base, far), writer, NullDlq())
    assert result.canonicals == 2 and result.grouped == 0
    assert _count(clean_db) == 2
    sources = _source_rows(clean_db)
    assert {cid for _, cid in sources} == {base.url_hash, far.url_hash}


# M1 TC-13 + M2a TC-12: retention deletes the canonical AND cascades its sources
def test_retention_deletes_only_older_than_seven_days(clean_db: str) -> None:
    now = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
    engine = make_engine(clean_db)
    with Session(engine) as session:
        for age_days, key in ((8, "old"), (6, "fresh")):
            session.add(Article(
                url_hash=key, gkg_record_id="x", slot=SLOT,
                url=f"https://e.com/{key}", title=key, domain=None,
                published_at=now, ingested_at=now - timedelta(days=age_days),
                themes=[], persons=[], orgs=[],
            ))  # fmt: skip
        session.commit()
    with Session(engine) as session:
        session.add(ArticleSource(
            url_hash="old-src", article_id="old", url="https://e.com/old2",
            domain=None, slot=SLOT, gkg_record_id="x", published_at=now,
        ))  # fmt: skip
        session.commit()
    deleted = SqlArticleWriter(engine).delete_ingested_before(cutoff(now))
    assert deleted == 1
    with Session(engine) as session:
        remaining = session.scalars(select(Article.url_hash)).all()
        orphan_sources = session.scalars(select(ArticleSource.url_hash)).all()
    assert remaining == ["fresh"]
    assert orphan_sources == []  # AC-11: sources cascade with the canonical
    engine.dispose()
