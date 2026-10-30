"""The two search legs over Postgres (role: api_rw): parameterized ORM queries only.

Vector leg: HNSW cosine over `articles.embedding`, restricted to rows embedded by the
configured model (rows from another model are never compared, AC-11). Keyword leg:
full-text on the title with the same expression as the GIN index (spec D-8). Both
use the one filter implementation of `adapters/repo.py`.
"""

from typing import Any

from newsdock_db.models import Article
from sqlalchemy import ColumnClause, Engine, Float, func, literal_column, select
from sqlalchemy.orm import Session

from newsdock_api.adapters.repo import SqlArticleRepo, apply_filters
from newsdock_api.domain.records import ArticleSummary
from newsdock_api.domain.semantic import Hit, SearchFilters

# a literal, so the planner can use the GIN index
_ENGLISH: ColumnClause[Any] = literal_column("'english'")


class SqlSemanticRepo:
    def __init__(self, engine: Engine, *, ef_search: int = 100) -> None:
        self._engine = engine
        self._ef_search = ef_search
        self._articles = SqlArticleRepo(engine)

    def vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        distance = Article.embedding.op("<=>", return_type=Float)(vector)
        inner = apply_filters(
            select(
                Article.url_hash.label("id"),
                Article.published_at.label("published_at"),
                distance.label("distance"),
            ).where(Article.embedding_model == model, Article.embedding.is_not(None)),
            time_from=filters.time_from,
            time_to=filters.time_to,
            theme=filters.theme,
            domain=filters.domain,
            text_filter=None,
        )
        ranked = inner.order_by(distance).limit(limit).subquery()
        # `relaxed_order` can return rows slightly out of order, so sort exactly outside
        outer = select(
            ranked.c.id, ranked.c.published_at, (1 - ranked.c.distance)
        ).order_by(ranked.c.distance, ranked.c.id)
        with Session(self._engine) as session:
            # iterative scan keeps scanning until enough rows pass the filters
            session.execute(
                select(func.set_config("hnsw.iterative_scan", "relaxed_order", True))
            )
            session.execute(
                select(func.set_config("hnsw.ef_search", str(self._ef_search), True))
            )
            rows = session.execute(outer).all()
        return [Hit(r[0], r[1], float(r[2])) for r in rows]

    def keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        document = func.to_tsvector(_ENGLISH, Article.title)
        wanted = func.websearch_to_tsquery(_ENGLISH, query)
        rank = func.ts_rank(document, wanted, type_=Float)
        statement = apply_filters(
            select(Article.url_hash, Article.published_at, rank.label("rank")).where(
                document.op("@@")(wanted)
            ),
            time_from=filters.time_from,
            time_to=filters.time_to,
            theme=filters.theme,
            domain=filters.domain,
            text_filter=None,
        )
        statement = statement.order_by(
            rank.desc(), Article.published_at.desc(), Article.url_hash
        ).limit(limit)
        with Session(self._engine) as session:
            rows = session.execute(statement).all()
        return [Hit(r[0], r[1]) for r in rows]

    def summaries(self, ids: list[str]) -> dict[str, ArticleSummary]:
        return self._articles.summaries(ids)
