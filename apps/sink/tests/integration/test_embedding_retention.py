"""TC-14 (AC-13): retention removes an embedded article together with its vector."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_db.engine import make_engine
from newsdock_db.models import Article
from newsdock_sink.adapters.db import SqlArticleWriter
from newsdock_sink.domain.retention import cutoff
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
MODEL = "nomic-embed-text"


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


def _article(key: str, now: datetime, age_days: int) -> Article:
    return Article(
        url_hash=key, gkg_record_id="x", slot="20261028120000",
        url=f"https://e.com/{key}", title=key, domain=None,
        published_at=now, ingested_at=now - timedelta(days=age_days),
        themes=[], persons=[], orgs=[],
        embedding=[0.5] * 768, embedding_model=MODEL,
    )  # fmt: skip


def test_retention_removes_the_embedded_row_and_keeps_the_fresh_one(
    engine: Engine,
) -> None:
    now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all([_article("old", now, 8), _article("fresh", now, 6)])
        session.commit()

    deleted = SqlArticleWriter(engine).delete_ingested_before(cutoff(now, 7))

    assert deleted == 1
    with Session(engine) as session:
        rows = session.execute(select(Article.url_hash, Article.embedding_model)).all()
        vectors = session.scalars(select(Article.embedding)).all()
    assert [tuple(r) for r in rows] == [("fresh", MODEL)]
    assert len(vectors) == 1 and vectors[0] is not None and len(vectors[0]) == 768
