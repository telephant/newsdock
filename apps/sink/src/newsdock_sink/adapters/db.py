"""Postgres writer (role: sink_rw): canonical/source upserts, retention delete."""

from datetime import datetime, timedelta

from newsdock_core.contracts import CleanArticle
from newsdock_db.models import Article, ArticleSource
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Executable

from newsdock_sink.domain.writer import DbUnavailable, RowRejected


def _article_values(article: CleanArticle, story_key: str) -> dict[str, object]:
    return {
        "url_hash": article.url_hash,
        "story_key": story_key,
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


def _source_values(article: CleanArticle, canonical_id: str) -> dict[str, object]:
    return {
        "url_hash": article.url_hash,
        "article_id": canonical_id,
        "url": article.url,
        "domain": article.domain,
        "slot": article.slot,
        "gkg_record_id": article.gkg_record_id,
        "published_at": article.published_at,
    }


class SqlArticleWriter:
    """Implements the sink's StoryWriter port plus the retention delete."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_canonical(
        self, story_key: str, published_at: datetime, window: timedelta
    ) -> tuple[str, datetime] | None:
        statement = (
            select(Article.url_hash, Article.published_at)
            .where(Article.story_key == story_key)
            .where(Article.published_at >= published_at - window)
            .where(Article.published_at <= published_at + window)
            .order_by(Article.published_at)
            .limit(1)
        )
        try:
            with Session(self._engine) as session:
                row = session.execute(statement).first()
                return (row[0], row[1]) if row is not None else None
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc

    def insert_canonical(self, article: CleanArticle, story_key: str) -> bool:
        statement = (
            insert(Article)
            .values(_article_values(article, story_key))
            .on_conflict_do_nothing(index_elements=["url_hash"])
            .returning(Article.url_hash)
        )
        return self._execute_returning(statement)

    def insert_source(self, article: CleanArticle, canonical_id: str) -> bool:
        statement = (
            insert(ArticleSource)
            .values(_source_values(article, canonical_id))
            .on_conflict_do_nothing(index_elements=["url_hash"])
            .returning(ArticleSource.url_hash)
        )
        return self._execute_returning(statement)

    def _execute_returning(self, statement: Executable) -> bool:
        try:
            with Session(self._engine) as session:
                inserted = session.execute(statement).scalars().all()
                session.commit()
                return len(inserted) > 0
        except OperationalError as exc:  # connection-level: back off, no commit
            raise DbUnavailable(str(exc)) from exc
        except (DataError, IntegrityError, ValueError) as exc:
            raise RowRejected(str(exc)) from exc

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
