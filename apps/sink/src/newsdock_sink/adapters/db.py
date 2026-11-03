"""Postgres writer (role: sink_rw): canonical/source upserts, retention delete."""

from datetime import datetime, timedelta

from newsdock_core.contracts import CleanArticle, CleanEvent, CleanMention
from newsdock_db.models import Article, ArticleSource, Event, Mention
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Executable

from newsdock_sink.domain.writer import Candidate, DbUnavailable, RowRejected


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

    def find_candidates(
        self, story_key: str, published_at: datetime, window: timedelta
    ) -> list[Candidate]:
        stories = (
            select(Article.url_hash, Article.published_at)
            .where(Article.story_key == story_key)
            .where(Article.published_at >= published_at - window)
            .where(Article.published_at <= published_at + window)
            .order_by(Article.published_at)
        )
        try:
            with Session(self._engine) as session:
                rows = session.execute(stories).all()
                if not rows:
                    return []
                members = session.execute(
                    select(
                        ArticleSource.article_id,
                        ArticleSource.domain,
                        ArticleSource.url,
                    ).where(ArticleSource.article_id.in_([r[0] for r in rows]))
                ).all()
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc
        by_story: dict[str, list[tuple[str | None, str]]] = {}
        for article_id, domain, url in members:
            by_story.setdefault(article_id, []).append((domain, url))
        return [Candidate(r[0], r[1], by_story.get(r[0], [])) for r in rows]

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


def _event_values(event: CleanEvent) -> dict[str, object]:
    geo = event.geo
    return {
        "event_id": event.event_id,
        "event_date": event.event_date,
        "is_root": event.is_root,
        "actor1_code": event.actor1.code,
        "actor1_name": event.actor1.name,
        "actor1_country": event.actor1.country,
        "actor1_type": event.actor1.type1,
        "actor2_code": event.actor2.code,
        "actor2_name": event.actor2.name,
        "actor2_country": event.actor2.country,
        "actor2_type": event.actor2.type1,
        "cameo_code": event.cameo_code,
        "cameo_base": event.cameo_base,
        "cameo_root": event.cameo_root,
        "quad_class": event.quad_class,
        "goldstein": event.goldstein,
        "num_mentions": event.num_mentions,
        "num_sources": event.num_sources,
        "num_articles": event.num_articles,
        "avg_tone": event.avg_tone,
        "geo_name": geo.name if geo else None,
        "geo_country": geo.country if geo else None,
        "geo_adm1": geo.adm1 if geo else None,
        "geo_lat": geo.lat if geo else None,
        "geo_lon": geo.lon if geo else None,
        "date_added": event.date_added,
        "source_url": event.source_url,
        "source_url_hash": event.source_url_hash,
    }


def _mention_values(mention: CleanMention) -> dict[str, object]:
    return {
        "event_id": mention.event_id,
        "url_hash": mention.url_hash,
        "url": mention.url,
        "source_name": mention.source_name,
        "mention_time": mention.mention_time,
        "confidence": mention.confidence,
    }


class SqlGdeltWriter:
    """Implements the sink's GdeltWriter port (role: sink_rw).

    A row is inserted, or replaced only when the incoming one is strictly newer
    (`date_added` for events, `mention_time` for mentions), so replays and older
    redeliveries change nothing and do not move `ingested_at` (retention).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert_events(self, events: list[CleanEvent]) -> int:
        if not events:
            return 0
        insert_statement = insert(Event).values([_event_values(e) for e in events])
        update_columns: dict[str, object] = {
            name: insert_statement.excluded[name]
            for name in _event_values(events[0])
            if name != "event_id"
        }
        update_columns["ingested_at"] = func.now()
        statement = insert_statement.on_conflict_do_update(
            index_elements=["event_id"],
            set_=update_columns,
            where=Event.date_added < insert_statement.excluded.date_added,
        ).returning(Event.event_id)
        return self._execute_returning_count(statement)

    def upsert_mentions(self, mentions: list[CleanMention]) -> int:
        if not mentions:
            return 0
        insert_statement = insert(Mention).values(
            [_mention_values(m) for m in mentions]
        )
        statement = insert_statement.on_conflict_do_update(
            index_elements=["event_id", "url_hash"],
            set_={
                "url": insert_statement.excluded.url,
                "source_name": insert_statement.excluded.source_name,
                "mention_time": insert_statement.excluded.mention_time,
                "confidence": insert_statement.excluded.confidence,
                "ingested_at": func.now(),
            },
            where=Mention.mention_time < insert_statement.excluded.mention_time,
        ).returning(Mention.event_id)
        return self._execute_returning_count(statement)

    def _execute_returning_count(self, statement: Executable) -> int:
        try:
            with Session(self._engine) as session:
                changed = session.execute(statement).scalars().all()
                session.commit()
                return len(changed)
        except OperationalError as exc:  # connection-level: back off, no commit
            raise DbUnavailable(str(exc)) from exc
        except (DataError, IntegrityError, ValueError) as exc:
            raise RowRejected(str(exc)) from exc

    def delete_ingested_before(self, cutoff: datetime) -> tuple[int, int]:
        """Retention for both tables on one cutoff; returns (events, mentions)."""
        try:
            with Session(self._engine) as session:
                events = session.execute(
                    delete(Event).where(Event.ingested_at < cutoff)
                )
                mentions = session.execute(
                    delete(Mention).where(Mention.ingested_at < cutoff)
                )
                session.commit()
                return (
                    int(getattr(events, "rowcount", 0) or 0),
                    int(getattr(mentions, "rowcount", 0) or 0),
                )
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc
