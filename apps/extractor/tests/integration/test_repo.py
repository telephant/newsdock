"""TC-13, TC-14, TC-15 (database half): queue, discovery and stores on real Postgres.

Runs against a throwaway Postgres from the `side_db` fixture (own compose project, free
port), so the dev stack's database is never touched.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_db.engine import make_engine
from newsdock_db.models import Article, ArticleBody, ArticlePassage
from newsdock_db.testing import article
from newsdock_extractor.adapters.db import SqlBodyRepo
from newsdock_extractor.domain.loop import DbUnavailable
from newsdock_extractor.domain.status import BodyStatus
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
# Rows get `next_attempt_at = now()` of the database, so the test clock must not be
# earlier than the real time: it is ten minutes ahead, whenever the test runs.
NOW = datetime.now(UTC) + timedelta(minutes=10)


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


def add(engine: Engine, key: str, *, age_hours: float = 1.0) -> str:
    """An article ingested `age_hours` ago; returns its url_hash."""
    row = article(key, f"title {key}", domain=f"{key}.example")
    row.url = f"https://{key}.example/story"
    row.ingested_at = NOW - timedelta(hours=age_hours)
    with Session(engine) as session:
        session.add(row)
        session.commit()
    return key


def bodies(engine: Engine) -> dict[str, ArticleBody]:
    with Session(engine) as session:
        rows = session.scalars(select(ArticleBody)).all()
        session.expunge_all()
    return {r.url_hash: r for r in rows}


# ---------------------------------------------------------------- discovery (TC-14)
def test_the_first_run_discovers_only_the_last_backfill_hours(clean: Engine) -> None:
    for key, age in (("new1", 1), ("new2", 5), ("old1", 10), ("old2", 100)):
        add(clean, key, age_hours=age)
    repo = SqlBodyRepo(clean)
    assert repo.discover(now=NOW, backfill_hours=6) == 2
    found = bodies(clean)
    assert set(found) == {"new1", "new2"}
    assert all(b.status == "pending" and b.attempts == 0 for b in found.values())
    assert found["new1"].created_at == NOW - timedelta(hours=1)  # the article's time
    with Session(clean) as session:
        seqs = dict(session.execute(select(Article.url_hash, Article.seq)).all())
    assert {k: b.seq for k, b in found.items()} == {k: seqs[k] for k in found}


def test_later_runs_follow_seq_and_never_back_fill_older_articles(
    clean: Engine,
) -> None:
    add(clean, "first", age_hours=1)
    repo = SqlBodyRepo(clean)
    assert repo.discover(now=NOW, backfill_hours=6) == 1
    add(clean, "second", age_hours=0.5)
    # an old article that only now enters the table has a higher seq: it is discovered
    add(clean, "late-but-old", age_hours=50)
    assert repo.discover(now=NOW, backfill_hours=6) == 2
    assert set(bodies(clean)) == {"first", "second", "late-but-old"}
    assert repo.discover(now=NOW, backfill_hours=6) == 0  # nothing new: idempotent
    assert len(bodies(clean)) == 3


def test_discovery_works_in_batches_and_loses_nothing(clean: Engine) -> None:
    for n in range(7):
        add(clean, f"b{n}", age_hours=1)
    repo = SqlBodyRepo(clean, discover_batch=3)
    assert [repo.discover(now=NOW, backfill_hours=6) for _ in range(4)] == [3, 3, 1, 0]
    assert len(bodies(clean)) == 7


def test_articles_already_in_the_queue_are_not_duplicated(clean: Engine) -> None:
    add(clean, "x", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    with Session(clean) as session:
        session.execute(text("UPDATE article_bodies SET status = 'ok'"))
        session.commit()
    repo.discover(now=NOW, backfill_hours=6)
    assert bodies(clean)["x"].status == "ok"  # untouched by a second discovery


# ---------------------------------------------------------------- the queue (TC-14)
def test_the_queue_is_newest_first_due_and_inside_the_window(clean: Engine) -> None:
    for key in ("a", "b", "c", "d", "e"):
        add(clean, key, age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    with Session(clean) as session:
        session.execute(
            text("UPDATE article_bodies SET created_at = :t WHERE url_hash = 'b'"),
            {"t": NOW - timedelta(days=8)},  # older than the window
        )
        session.execute(
            text("UPDATE article_bodies SET next_attempt_at = :t WHERE url_hash = 'c'"),
            {"t": NOW + timedelta(minutes=5)},  # waiting for a retry
        )
        session.execute(
            text("UPDATE article_bodies SET status = 'ok' WHERE url_hash = 'd'")
        )
        session.commit()
    rows = repo.next_batch(now=NOW, retention_days=7, limit=10)
    assert [r.url_hash for r in rows] == ["e", "a"]  # newest seq first
    assert all(r.url == f"https://{r.url_hash}.example/story" for r in rows)
    assert rows[0].seq > rows[1].seq
    assert [
        r.url_hash for r in repo.next_batch(now=NOW, retention_days=7, limit=1)
    ] == ["e"]


def test_a_row_that_is_due_again_comes_back(clean: Engine) -> None:
    add(clean, "a", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    repo.store_retry(
        "a",
        status=BodyStatus.pending,
        attempts=1,
        next_attempt_at=NOW + timedelta(minutes=5),
        http_status=500,
    )
    assert repo.next_batch(now=NOW, retention_days=7, limit=10) == []
    later = NOW + timedelta(minutes=5, seconds=1)
    (row,) = repo.next_batch(now=later, retention_days=7, limit=10)
    assert row.attempts == 1


def test_the_queue_query_can_use_the_partial_index(clean: Engine) -> None:
    for n in range(300):
        add(clean, f"p{n}", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    with Session(clean) as session:
        session.execute(text("ANALYZE article_bodies"))
        session.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in session.execute(
                text(
                    "EXPLAIN SELECT url_hash FROM article_bodies "
                    "WHERE status = 'pending' AND next_attempt_at <= now() "
                    "AND created_at >= now() - interval '7 days' "
                    "ORDER BY seq DESC LIMIT 200"
                )
            )
        )
    assert "ix_article_bodies_pending" in plan, plan


# ---------------------------------------------------------------- stores (TC-13)
def test_store_ok_writes_the_text_and_the_passages_once(clean: Engine) -> None:
    add(clean, "a", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    assert repo.store_ok(
        "a",
        text="full text",
        passages=["first piece", "second piece"],
        http_status=200,
        fetched_at=NOW,
        attempts=1,
    )
    body = bodies(clean)["a"]
    assert (body.status, body.text, body.http_status, body.attempts) == (
        "ok",
        "full text",
        200,
        1,
    )
    assert body.fetched_at == NOW
    with Session(clean) as session:
        passages = session.scalars(
            select(ArticlePassage).order_by(ArticlePassage.idx)
        ).all()
        assert [(p.idx, p.text, p.embedding, p.embedding_model) for p in passages] == [
            (0, "first piece", None, None),
            (1, "second piece", None, None),
        ]
    # a second worker with the same page: nothing changes, no duplicate passages
    assert not repo.store_ok(
        "a",
        text="other",
        passages=["x", "y", "z"],
        http_status=200,
        fetched_at=NOW,
        attempts=2,
    )
    again = bodies(clean)["a"]
    assert again.text == "full text" and again.attempts == 1
    with Session(clean) as session:
        assert session.scalar(text("SELECT count(*) FROM article_passages")) == 2


@pytest.mark.parametrize(
    "status",
    [
        BodyStatus.blocked_robots,
        BodyStatus.blocked_address,
        BodyStatus.http_error,
        BodyStatus.not_html,
        BodyStatus.too_large,
        BodyStatus.no_text,
        BodyStatus.failed,
    ],
)
def test_store_final_records_the_status_and_no_text(
    clean: Engine, status: BodyStatus
) -> None:
    add(clean, "a", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    assert repo.store_final(
        "a", status=status, http_status=403, fetched_at=NOW, attempts=1
    )
    body = bodies(clean)["a"]
    assert (body.status, body.http_status, body.text, body.attempts) == (
        status.value,
        403,
        None,
        1,
    )
    assert repo.next_batch(now=NOW, retention_days=7, limit=10) == []


def test_every_store_only_changes_a_pending_row(clean: Engine) -> None:
    add(clean, "a", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    assert repo.store_ok(
        "a",
        text="t",
        passages=["p"],
        http_status=200,
        fetched_at=NOW,
        attempts=1,
    )
    assert not repo.store_final(
        "a", status=BodyStatus.no_text, http_status=200, fetched_at=NOW, attempts=2
    )
    assert not repo.store_retry(
        "a", status=BodyStatus.pending, attempts=2, next_attempt_at=NOW, http_status=500
    )
    assert not repo.defer("a", next_attempt_at=NOW + timedelta(hours=1))
    body = bodies(clean)["a"]
    assert (body.status, body.text, body.attempts) == ("ok", "t", 1)


def test_defer_moves_only_the_next_attempt(clean: Engine) -> None:
    add(clean, "a", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    later = NOW + timedelta(minutes=60)
    assert repo.defer("a", next_attempt_at=later)
    body = bodies(clean)["a"]
    assert (body.status, body.attempts, body.next_attempt_at) == ("pending", 0, later)


def test_a_failed_retry_state_is_final(clean: Engine) -> None:
    add(clean, "a", age_hours=1)
    repo = SqlBodyRepo(clean)
    repo.discover(now=NOW, backfill_hours=6)
    assert repo.store_retry(
        "a",
        status=BodyStatus.failed,
        attempts=3,
        next_attempt_at=None,
        http_status=503,
    )
    body = bodies(clean)["a"]
    assert (body.status, body.attempts, body.http_status) == ("failed", 3, 503)
    assert repo.next_batch(now=NOW, retention_days=7, limit=10) == []


# ---------------------------------------------------------------- retention (TC-15)
def test_deleting_old_articles_removes_their_bodies_and_passages(clean: Engine) -> None:
    add(clean, "old", age_hours=24 * 8)
    add(clean, "new", age_hours=1)
    repo = SqlBodyRepo(clean)
    with Session(clean) as session:  # both are in the queue (a long-running worker)
        session.execute(
            text(
                "INSERT INTO article_bodies (url_hash, seq, created_at) "
                "SELECT url_hash, seq, ingested_at FROM articles"
            )
        )
        session.commit()
    for key in ("old", "new"):
        assert repo.store_ok(
            key,
            text=f"text {key}",
            passages=["p0", "p1"],
            http_status=200,
            fetched_at=NOW,
            attempts=1,
        )
    with Session(clean) as session:  # the sink's retention statement
        session.execute(
            delete(Article).where(Article.ingested_at < NOW - timedelta(days=7))
        )
        session.commit()
        assert set(bodies(clean)) == {"new"}
        remaining = session.scalars(select(ArticlePassage.url_hash)).all()
        assert sorted(remaining) == ["new", "new"]


# ---------------------------------------------------------------- outages
def test_a_database_outage_is_reported_as_db_unavailable(
    side_db: tuple[
        str, str
    ],  # takes the fixture so the dev-stack guard stays satisfied
) -> None:
    dead = make_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/none")
    repo = SqlBodyRepo(dead)
    with pytest.raises(DbUnavailable):
        repo.discover(now=NOW, backfill_hours=6)
    with pytest.raises(DbUnavailable):
        repo.next_batch(now=NOW, retention_days=7, limit=1)
    with pytest.raises(DbUnavailable):
        repo.defer("a", next_attempt_at=NOW)
    dead.dispose()
