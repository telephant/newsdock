"""Postgres repository (role: api_rw): parameterized ORM queries only (DR-9)."""

from datetime import datetime
from typing import Any

from newsdock_db.models import Analysis, Article, IngestSlot
from sqlalchemy import Engine, Select, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from newsdock_api.domain.records import AnalysisRecord, ArticleDetail, ArticleSummary
from newsdock_api.domain.service import escape_like


def _summary(row: Article, scores: dict[str, float] | None = None) -> ArticleSummary:
    return ArticleSummary(
        article_id=row.url_hash,
        title=row.title,
        url=row.url,
        domain=row.domain,
        published_at=row.published_at,
        themes=row.themes,
        seq=row.seq,
        scores=scores,
    )


def _apply_filters(
    statement: Select[Article],
    *,
    time_from: datetime | None,
    time_to: datetime | None,
    theme: str | None,
    domain: str | None,
    text_filter: str | None,
) -> Select[Article]:
    if time_from is not None:
        statement = statement.where(Article.published_at >= time_from)
    if time_to is not None:
        statement = statement.where(Article.published_at <= time_to)
    if theme is not None:
        statement = statement.where(Article.themes.contains([theme]))
    if domain is not None:
        statement = statement.where(Article.domain == domain)
    if text_filter is not None:
        statement = statement.where(
            Article.title.ilike(f"%{escape_like(text_filter)}%", escape="\\")
        )
    return statement


class SqlArticleRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

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
    ) -> list[ArticleSummary]:
        statement = (
            _apply_filters(
                select(Article),
                time_from=time_from,
                time_to=time_to,
                theme=theme,
                domain=domain,
                text_filter=text,
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
            scores = self._scores(session, [r.url_hash for r in rows])
            return [_summary(r, scores.get(r.url_hash)) for r in rows]

    def list_new(
        self, *, after_seq: int | None, since: datetime | None, limit: int
    ) -> list[ArticleSummary]:
        statement = select(Article).order_by(Article.seq).limit(limit)
        if after_seq is not None:
            statement = statement.where(Article.seq > after_seq)
        if since is not None:
            statement = statement.where(Article.ingested_at >= since)
        with Session(self._engine) as session:
            rows: list[Article] = list(session.scalars(statement).all())
            return [_summary(r) for r in rows]

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
                word_count=row.word_count,
                analyses=[
                    AnalysisRecord(
                        agent_name=a.agent_name,
                        payload=a.payload,
                        created_at=a.created_at,
                    )
                    for a in analyses
                ],
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
