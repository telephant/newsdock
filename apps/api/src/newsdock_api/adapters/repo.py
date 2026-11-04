"""Postgres repository (role: api_rw): parameterized ORM queries only (DR-9)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, TypeVar

from newsdock_db.models import (
    Analysis,
    Article,
    ArticleBody,
    ArticleSource,
    Event,
    IngestSlot,
    Mention,
)
from sqlalchemy import REAL, Engine, Select, cast, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from newsdock_api.domain.include import BODY_FIELD, EVENTS_FIELD, TONE_FIELDS
from newsdock_api.domain.records import (
    AnalysisRecord,
    ArticleDetail,
    ArticleSummary,
    EventActor,
    EventLocation,
    EventOut,
    SourceRecord,
)
from newsdock_api.domain.service import escape_like
from newsdock_api.domain.subscriptions import split_theme

DEFAULT_EVENTS_PER_ARTICLE = 20


def _event_out(event: Event, mention_count: int) -> EventOut:
    has_place = any(
        v is not None
        for v in (
            event.geo_name,
            event.geo_country,
            event.geo_adm1,
            event.geo_lat,
            event.geo_lon,
        )
    )
    return EventOut(
        event_id=event.event_id,
        date=event.event_date,
        cameo_code=event.cameo_code,
        cameo_root=event.cameo_root,
        goldstein=event.goldstein,
        quad_class=event.quad_class,
        num_mentions=event.num_mentions,
        num_sources=event.num_sources,
        avg_tone=event.avg_tone,
        actor1=EventActor(
            code=event.actor1_code,
            name=event.actor1_name,
            country=event.actor1_country,
            type=event.actor1_type,
        ),
        actor2=EventActor(
            code=event.actor2_code,
            name=event.actor2_name,
            country=event.actor2_country,
            type=event.actor2_type,
        ),
        location=(
            EventLocation(
                name=event.geo_name,
                country=event.geo_country,
                adm1=event.geo_adm1,
                lat=event.geo_lat,
                lon=event.geo_lon,
            )
            if has_place
            else None
        ),
        source_url=event.source_url,
        mention_count=mention_count,
    )


def _summary(
    row: Article,
    scores: dict[str, float] | None = None,
    source_count: int = 1,
    include: Sequence[str] = (),
    events: list[EventOut] | None = None,
    body: str | None = None,
) -> ArticleSummary:
    # only what was asked for: tone numbers by name, events when `events` was given
    tone = {name: getattr(row, name) for name in include if name in TONE_FIELDS}
    return ArticleSummary(
        article_id=row.url_hash,
        title=row.title,
        url=row.url,
        domain=row.domain,
        published_at=row.published_at,
        themes=row.themes,
        seq=row.seq,
        scores=scores,
        source_count=source_count,
        events=events,
        body=body,
        **tone,
    )


_S = TypeVar("_S", bound=Select[Any])


def apply_filters(
    statement: _S,
    *,
    time_from: datetime | None,
    time_to: datetime | None,
    theme: str | None,
    domain: str | None,
    text_filter: str | None,
    min_negativity: float | None = None,
) -> _S:
    """The one implementation of the search filters (also used by semantic search)."""
    if time_from is not None:
        statement = statement.where(Article.published_at >= time_from)
    if time_to is not None:
        statement = statement.where(Article.published_at <= time_to)
    if theme is not None:
        value, is_prefix = split_theme(theme)
        if is_prefix:  # `ECON_*`: any of the article's themes starts with the prefix
            each = func.unnest(Article.themes).table_valued("theme").render_derived()
            has_prefix = (
                select(literal(1))
                .select_from(each)
                .where(each.c.theme.like(escape_like(value) + "%", escape="\\"))
                .exists()
            )
            statement = statement.where(has_prefix)
        else:
            statement = statement.where(Article.themes.contains([value]))
    if domain is not None:
        statement = statement.where(Article.domain == domain)
    if text_filter is not None:
        statement = statement.where(
            Article.title.ilike(f"%{escape_like(text_filter)}%", escape="\\")
        )
    if min_negativity is not None:
        # `tone_neg` is a float4: compare it with a float4 so a typed 9.7 equals the
        # stored 9.7 (a float8 parameter would be larger). NULL >= x is not true, so
        # articles without tone drop out.
        statement = statement.where(
            Article.tone_neg >= cast(literal(min_negativity), REAL)
        )
    return statement


class SqlArticleRepo:
    def __init__(
        self, engine: Engine, *, events_per_article: int = DEFAULT_EVENTS_PER_ARTICLE
    ) -> None:
        self._engine = engine
        self._events_per_article = events_per_article

    def search(
        self,
        *,
        time_from: datetime | None,
        time_to: datetime | None,
        theme: str | None,
        domain: str | None,
        text: str | None,
        limit: int,
        before: tuple[datetime, str] | None = None,
        min_negativity: float | None = None,
        include: Sequence[str] = (),
    ) -> list[ArticleSummary]:
        statement = (
            apply_filters(
                select(Article),
                time_from=time_from,
                time_to=time_to,
                theme=theme,
                domain=domain,
                text_filter=text,
                min_negativity=min_negativity,
            )
            .order_by(Article.published_at.desc(), Article.url_hash)
            .limit(limit)
        )
        if before is not None:  # keyset pagination (design-detail §3)
            published_at, url_hash = before
            statement = statement.where(
                (Article.published_at < published_at)
                | (
                    (Article.published_at == published_at)
                    & (Article.url_hash > url_hash)
                )
            )
        with Session(self._engine) as session:
            rows: list[Article] = list(session.scalars(statement).all())
            ids = [r.url_hash for r in rows]
            scores = self._scores(session, ids)
            counts = self._source_counts(session, ids)
            events = self._events_if_asked(session, ids, include)
            bodies = self._bodies_if_asked(session, ids, include)
            return [
                _summary(
                    r,
                    scores.get(r.url_hash),
                    counts.get(r.url_hash, 1),
                    include,
                    events.get(r.url_hash),
                    bodies.get(r.url_hash),
                )
                for r in rows
            ]

    def summaries(
        self, article_ids: list[str], include: Sequence[str] = ()
    ) -> dict[str, ArticleSummary]:
        """Summaries (with scores and source counts); unknown ids are absent."""
        if not article_ids:
            return {}
        with Session(self._engine) as session:
            rows: list[Article] = list(
                session.scalars(
                    select(Article).where(Article.url_hash.in_(article_ids))
                ).all()
            )
            ids = [r.url_hash for r in rows]
            scores = self._scores(session, ids)
            counts = self._source_counts(session, ids)
            events = self._events_if_asked(session, ids, include)
            bodies = self._bodies_if_asked(session, ids, include)
            return {
                r.url_hash: _summary(
                    r,
                    scores.get(r.url_hash),
                    counts.get(r.url_hash, 1),
                    include,
                    events.get(r.url_hash),
                    bodies.get(r.url_hash),
                )
                for r in rows
            }

    def latest_seq(self) -> int | None:
        with Session(self._engine) as session:
            newest = session.scalar(select(func.max(Article.seq)))
            return int(newest) if newest is not None else None

    def list_new(
        self,
        *,
        after_seq: int | None,
        since: datetime | None,
        limit: int,
        theme: str | None = None,
        domain: str | None = None,
        text: str | None = None,
        min_negativity: float | None = None,
        include: Sequence[str] = (),
    ) -> list[ArticleSummary]:
        statement = apply_filters(
            select(Article),
            time_from=None,
            time_to=None,
            theme=theme,
            domain=domain,
            text_filter=text,
            min_negativity=min_negativity,
        )
        statement = statement.order_by(Article.seq).limit(limit)
        if after_seq is not None:
            statement = statement.where(Article.seq > after_seq)
        if since is not None:
            statement = statement.where(Article.ingested_at >= since)
        with Session(self._engine) as session:
            rows: list[Article] = list(session.scalars(statement).all())
            ids = [r.url_hash for r in rows]
            counts = self._source_counts(session, ids)
            events = self._events_if_asked(session, ids, include)
            bodies = self._bodies_if_asked(session, ids, include)
            return [
                _summary(
                    r,
                    source_count=counts.get(r.url_hash, 1),
                    include=include,
                    events=events.get(r.url_hash),
                    body=bodies.get(r.url_hash),
                )
                for r in rows
            ]

    def get(self, article_id: str) -> ArticleDetail | None:
        with Session(self._engine) as session:
            row = session.get(Article, article_id)
            if row is None:
                return None
            analyses = session.scalars(
                select(Analysis)
                .where(Analysis.article_id == article_id)
                .order_by(Analysis.agent_name)
            ).all()
            sources = session.scalars(
                select(ArticleSource)
                .where(ArticleSource.article_id == article_id)
                .order_by(ArticleSource.published_at)
            ).all()
            events = self._events_for(session, [article_id]).get(article_id, [])
            stored = session.execute(
                select(ArticleBody.status, ArticleBody.text).where(
                    ArticleBody.url_hash == article_id
                )
            ).first()
            body_status = stored[0] if stored else "none"
            body = stored[1] if stored and stored[0] == "ok" else None
            return ArticleDetail(
                article_id=row.url_hash,
                title=row.title,
                url=row.url,
                domain=row.domain,
                published_at=row.published_at,
                ingested_at=row.ingested_at,
                slot=row.slot,
                themes=row.themes,
                persons=row.persons,
                orgs=row.orgs,
                tone=row.tone,
                tone_pos=row.tone_pos,
                tone_neg=row.tone_neg,
                tone_polarity=row.tone_polarity,
                word_count=row.word_count,
                analyses=[
                    AnalysisRecord(
                        agent_name=a.agent_name,
                        payload=a.payload,
                        created_at=a.created_at,
                    )
                    for a in analyses
                ],
                sources=[
                    SourceRecord(
                        url=src.url,
                        domain=src.domain,
                        published_at=src.published_at,
                    )
                    for src in sources
                ],
                source_count=max(len(sources), 1),  # pre-feature rows: 1
                events=events,
                body=body,
                body_status=body_status,
            )

    def upsert_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, Any]
    ) -> bool:
        with Session(self._engine) as session:
            exists = session.get(Article, article_id)
            if exists is None:
                return False
            statement = (
                insert(Analysis)
                .values(article_id=article_id, agent_name=agent_name, payload=payload)
                .on_conflict_do_update(  # resubmission replaces (latest wins)
                    index_elements=["article_id", "agent_name"],
                    set_={"payload": payload, "created_at": func.now()},
                )
            )
            session.execute(statement)
            session.commit()
            return True

    def _bodies_if_asked(
        self, session: Session, article_ids: list[str], include: Sequence[str]
    ) -> dict[str, str | None]:
        """Page text per article, only when `include` names it (else no query runs).

        The text is given only for an `ok` row; a pending, failed or missing row is
        None (the detail route says which through `body_status`)."""
        if BODY_FIELD not in include or not article_ids:
            return {}
        rows = session.execute(
            select(ArticleBody.url_hash, ArticleBody.text).where(
                ArticleBody.url_hash.in_(article_ids), ArticleBody.status == "ok"
            )
        ).all()
        return {str(url_hash): body for url_hash, body in rows}

    def _events_if_asked(
        self, session: Session, article_ids: list[str], include: Sequence[str]
    ) -> dict[str, list[EventOut]]:
        """Events per article, only when `include` names them (else no query runs)."""
        if EVENTS_FIELD not in include:
            return {}
        found = self._events_for(session, article_ids)
        return {article_id: found.get(article_id, []) for article_id in article_ids}

    def _events_for(
        self, session: Session, article_ids: list[str]
    ) -> dict[str, list[EventOut]]:
        """The events each article is mentioned in, one query per page (ADR-0033).

        Joins `mentions` to `events` on `event_id` (no foreign key, so an event we have
        not stored yet is simply absent). Per article: most mentioned first, then by
        id, cut to `events_per_article`. `mention_count` counts the stored real
        mentions; the sink's derived rows for copies are not counted (ADR-0038).
        """
        if not article_ids:
            return {}
        others = aliased(Mention)
        mention_count = (
            select(func.count())
            .select_from(others)
            .where(others.event_id == Event.event_id, others.derived.is_(False))
            .scalar_subquery()
        )
        rows = session.execute(
            select(Mention.url_hash, Event, mention_count)
            .join(Event, Event.event_id == Mention.event_id)
            .where(Mention.url_hash.in_(article_ids))
            .order_by(Mention.url_hash, Event.num_mentions.desc(), Event.event_id)
        ).all()
        out: dict[str, list[EventOut]] = {}
        for url_hash, event, count in rows:
            found = out.setdefault(str(url_hash), [])
            if len(found) < self._events_per_article:
                found.append(_event_out(event, int(count)))
        return out

    def _source_counts(
        self, session: Session, article_ids: list[str]
    ) -> dict[str, int]:
        """Copies per story, one grouped query per page (design-detail §3)."""
        if not article_ids:
            return {}
        rows = session.execute(
            select(ArticleSource.article_id, func.count())
            .where(ArticleSource.article_id.in_(article_ids))
            .group_by(ArticleSource.article_id)
        ).all()
        return {str(article_id): max(int(n), 1) for article_id, n in rows}

    def _scores(
        self, session: Session, article_ids: list[str]
    ) -> dict[str, dict[str, float]]:
        """Latest numeric `payload.score` per agent, for the UI feed."""
        if not article_ids:
            return {}
        rows = session.scalars(
            select(Analysis).where(Analysis.article_id.in_(article_ids))
        ).all()
        out: dict[str, dict[str, float]] = {}
        for analysis in rows:
            score = analysis.payload.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                out.setdefault(analysis.article_id, {})[analysis.agent_name] = float(
                    score
                )
        return out

    def health(self) -> dict[str, Any]:
        try:
            with Session(self._engine) as session:
                session.execute(text("SELECT 1"))
                last_slot = session.scalar(
                    select(IngestSlot.slot)
                    .where(IngestSlot.status == "published")
                    .order_by(IngestSlot.slot.desc())
                    .limit(1)
                )
            return {"db": True, "last_published_slot": last_slot}
        except Exception:  # noqa: BLE001 — health must not raise
            return {"db": False, "last_published_slot": None}
