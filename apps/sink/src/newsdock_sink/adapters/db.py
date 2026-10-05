"""Postgres writer (role: sink_rw): idempotent upserts and the retention delete."""

from datetime import datetime

from newsdock_core.contracts import CleanArticle
from newsdock_db.models import Article
from sqlalchemy import Engine, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from newsdock_sink.domain.writer import DbUnavailable, RowRejected


def _values(article: CleanArticle) -> dict[str, object]:
    return {
        "url_hash": article.url_hash,
        "gkg_record_id": article.gkg_record_id,
        "slot": article.slot,
        "url": article.url,
        "title": article.title,
        "domain": article.domain,
        "published_at": article.published_at,
        "themes": article.themes,
        "persons": article.persons,
        "orgs": article.orgs,
        "tone": article.tone.tone,
        "tone_pos": article.tone.positive,
        "tone_neg": article.tone.negative,
        "tone_polarity": article.tone.polarity,
        "word_count": article.tone.word_count,
    }


class SqlArticleWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _insert(self, rows: list[dict[str, object]]) -> int:
        statement = (
            insert(Article)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["url_hash"])
            .returning(Article.url_hash)  # rowcount is unreliable for multi-row
        )
        try:
            with Session(self._engine) as session:
                inserted = session.execute(statement).scalars().all()
                session.commit()
                return len(inserted)
        except OperationalError as exc:  # connection-level: back off, no commit
            raise DbUnavailable(str(exc)) from exc
        except (DataError, IntegrityError, ValueError) as exc:
            raise RowRejected(str(exc)) from exc

    def insert_batch(self, articles: list[CleanArticle]) -> int:
        if not articles:
            return 0
        return self._insert([_values(a) for a in articles])

    def insert_one(self, article: CleanArticle) -> int:
        return self._insert([_values(article)])

    def delete_ingested_before(self, cutoff: datetime) -> int:
        try:
            with Session(self._engine) as session:
                result = session.execute(
                    delete(Article).where(Article.ingested_at < cutoff)
                )
                session.commit()
                return int(getattr(result, "rowcount", 0) or 0)
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc
