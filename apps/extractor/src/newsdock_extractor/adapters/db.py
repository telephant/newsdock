"""Postgres repository for the extractor (role `extractor_rw`, ADR-0036).

The queue is `article_bodies` rows in status `pending`, read newest first through the
partial index. Discovery creates those rows from `articles` by following `seq` (no
trigger, no change to the sink). Every store changes a row only while it is still
`pending`, so a duplicate delivery or a second worker cannot overwrite a result, and a
body's passages are inserted in the same transaction as its text.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from newsdock_db.models import Article, ArticleBody, ArticlePassage
from sqlalchemy import Engine, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import ColumnClause

from newsdock_extractor.domain.loop import DbUnavailable
from newsdock_extractor.domain.picking import QueueRow, window_start
from newsdock_extractor.domain.status import BodyStatus

# A literal, not a bound parameter: the planner must see the constant to use the partial
# index `ix_article_bodies_pending`, also after a prepared statement switches plans.
PENDING: ColumnClause[str] = literal_column("'pending'")


def _clean(text: str) -> str:
    """Postgres refuses NUL characters in text."""
    return text.replace("\x00", "")


class SqlBodyRepo:
    def __init__(self, engine: Engine, *, discover_batch: int = 1000) -> None:
        self._engine = engine
        self._batch = discover_batch

    @contextmanager
    def _session(self) -> Iterator[Session]:
        try:
            with Session(self._engine) as session:
                yield session
        except OperationalError as exc:  # connection-level: the worker backs off
            raise DbUnavailable(str(exc)) from exc

    # ------------------------------------------------------------------ discovery
    def discover(self, *, now: datetime, backfill_hours: int) -> int:
        """Queue the articles that have no body row yet; returns how many were queued.

        After the first run it follows `seq` past `max(article_bodies.seq)`; on an empty
        table it starts with the articles of the last `backfill_hours` only (no
        back-fill of older ones). `created_at` is the article's own ingestion time, so
        the retention window applies to the article, not to the discovery."""
        with self._session() as session:
            cursor = session.scalar(select(func.max(ArticleBody.seq)))
            wanted = select(Article.url_hash, Article.seq, Article.ingested_at)
            if cursor is None:
                since = now - timedelta(hours=backfill_hours)
                wanted = wanted.where(Article.ingested_at >= since)
            else:
                wanted = wanted.where(Article.seq > cursor)
            wanted = wanted.order_by(Article.seq).limit(self._batch)
            queued = session.execute(
                insert(ArticleBody)
                .from_select(["url_hash", "seq", "created_at"], wanted)
                .on_conflict_do_nothing(index_elements=["url_hash"])
                .returning(ArticleBody.url_hash)  # `rowcount` is -1 for this statement
            ).all()
            session.commit()
            return len(queued)

    # ------------------------------------------------------------------ the queue
    def next_batch(
        self, *, now: datetime, retention_days: int, limit: int
    ) -> list[QueueRow]:
        """Due rows inside the retention window, newest first."""
        with self._session() as session:
            rows = session.execute(
                select(
                    ArticleBody.url_hash,
                    Article.url,
                    ArticleBody.seq,
                    ArticleBody.created_at,
                    ArticleBody.next_attempt_at,
                    ArticleBody.attempts,
                )
                .join(Article, Article.url_hash == ArticleBody.url_hash)
                .where(
                    ArticleBody.status == PENDING,
                    ArticleBody.next_attempt_at <= now,
                    ArticleBody.created_at
                    >= window_start(now, retention_days=retention_days),
                )
                .order_by(ArticleBody.seq.desc())
                .limit(limit)
            ).all()
        return [
            QueueRow(
                url_hash=str(r[0]),
                url=str(r[1]),
                seq=int(r[2]),
                created_at=r[3],
                next_attempt_at=r[4],
                attempts=int(r[5]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ stores
    def _update_pending(
        self, session: Session, url_hash: str, values: dict[str, object]
    ) -> bool:
        updated = session.execute(
            update(ArticleBody)
            .where(ArticleBody.url_hash == url_hash, ArticleBody.status == PENDING)
            .values(**values)
            .returning(ArticleBody.url_hash)
        ).scalar_one_or_none()
        return updated is not None

    def store_ok(
        self,
        url_hash: str,
        *,
        text: str,
        passages: list[str],
        http_status: int,
        fetched_at: datetime,
        attempts: int,
    ) -> bool:
        """The text and its passages, in one transaction; False if the row is not
        pending any more (nothing is changed then)."""
        with self._session() as session:
            changed = self._update_pending(
                session,
                url_hash,
                {
                    "status": BodyStatus.ok.value,
                    "text": _clean(text),
                    "http_status": http_status,
                    "fetched_at": fetched_at,
                    "attempts": attempts,
                },
            )
            if not changed:
                session.rollback()
                return False
            if passages:
                session.execute(
                    insert(ArticlePassage)
                    .values(
                        [
                            {"url_hash": url_hash, "idx": index, "text": _clean(piece)}
                            for index, piece in enumerate(passages)
                        ]
                    )
                    .on_conflict_do_nothing(index_elements=["url_hash", "idx"])
                )
            session.commit()
            return True

    def store_final(
        self,
        url_hash: str,
        *,
        status: BodyStatus,
        http_status: int | None,
        fetched_at: datetime,
        attempts: int,
    ) -> bool:
        with self._session() as session:
            changed = self._update_pending(
                session,
                url_hash,
                {
                    "status": status.value,
                    "http_status": http_status,
                    "fetched_at": fetched_at,
                    "attempts": attempts,
                },
            )
            session.commit()
            return changed

    def store_retry(
        self,
        url_hash: str,
        *,
        status: BodyStatus,
        attempts: int,
        next_attempt_at: datetime | None,
        http_status: int | None,
    ) -> bool:
        """A transient failure: stay `pending` for a later try, or become `failed`."""
        values: dict[str, object] = {
            "status": status.value,
            "attempts": attempts,
            "http_status": http_status,
        }
        if next_attempt_at is not None:
            values["next_attempt_at"] = next_attempt_at
        with self._session() as session:
            changed = self._update_pending(session, url_hash, values)
            session.commit()
            return changed

    def defer(self, url_hash: str, *, next_attempt_at: datetime) -> bool:
        """Wait without counting an attempt (robots.txt could not be read)."""
        with self._session() as session:
            changed = self._update_pending(
                session, url_hash, {"next_attempt_at": next_attempt_at}
            )
            session.commit()
            return changed
