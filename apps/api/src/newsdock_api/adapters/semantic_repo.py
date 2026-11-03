"""The two search legs over Postgres (role: api_rw): parameterized ORM queries only.

Vector leg: HNSW cosine over `articles.embedding`, restricted to rows embedded by the
configured model (rows from another model are never compared, AC-11). Keyword leg:
full-text on the title with the same expression as the GIN index (spec D-8). Both
use the one filter implementation of `adapters/repo.py`.
"""

from collections.abc import Sequence
from typing import Any

from newsdock_db.models import Article, ArticlePassage
from sqlalchemy import ColumnClause, Engine, Float, func, literal_column, select
from sqlalchemy.orm import Session

from newsdock_api.adapters.repo import SqlArticleRepo, apply_filters
from newsdock_api.domain.records import ArticleSummary
from newsdock_api.domain.semantic import Hit, SearchFilters

# a literal, so the planner can use the GIN index
_ENGLISH: ColumnClause[Any] = literal_column("'english'")


class SqlSemanticRepo:
    def __init__(
        self,
        engine: Engine,
        *,
        ef_search: int = 100,
        events_per_article: int = 20,
        passage_candidates: int = 150,
    ) -> None:
        self._engine = engine
        self._ef_search = ef_search
        self._passage_candidates = passage_candidates
        self._articles = SqlArticleRepo(engine, events_per_article=events_per_article)

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
            min_negativity=filters.min_negativity,
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
            min_negativity=filters.min_negativity,
        )
        statement = statement.order_by(
            rank.desc(), Article.published_at.desc(), Article.url_hash
        ).limit(limit)
        with Session(self._engine) as session:
            rows = session.execute(statement).all()
        return [Hit(r[0], r[1]) for r in rows]

    def passage_vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        """Nearest passages of `model`, folded to the best passage per article."""
        distance = ArticlePassage.embedding.op("<=>", return_type=Float)(vector)
        statement = apply_filters(
            select(
                ArticlePassage.url_hash,
                Article.published_at,
                ArticlePassage.text,
                distance.label("distance"),
            )
            .join(Article, Article.url_hash == ArticlePassage.url_hash)
            .where(
                ArticlePassage.embedding_model == model,
                ArticlePassage.embedding.is_not(None),
            ),
            time_from=filters.time_from,
            time_to=filters.time_to,
            theme=filters.theme,
            domain=filters.domain,
            text_filter=None,
            min_negativity=filters.min_negativity,
        )
        # `relaxed_order` may return rows slightly out of order: sort exactly in SQL
        # over the candidate rows, then keep the first (nearest) passage per article
        ranked = statement.order_by(distance).limit(self._passage_candidates).subquery()
        outer = select(ranked).order_by(ranked.c.distance, ranked.c.url_hash)
        with Session(self._engine) as session:
            session.execute(
                select(func.set_config("hnsw.iterative_scan", "relaxed_order", True))
            )
            session.execute(
                select(func.set_config("hnsw.ef_search", str(self._ef_search), True))
            )
            rows = session.execute(outer).all()
        out: list[Hit] = []
        seen: set[str] = set()
        for url_hash, published_at, passage, dist in rows:
            if url_hash in seen:
                continue
            seen.add(url_hash)
            out.append(Hit(url_hash, published_at, 1 - float(dist), passage))
            if len(out) == limit:
                break
        return out

    def passage_keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        """Full-text matches on a passage (same expression as its GIN index)."""
        document = func.to_tsvector(_ENGLISH, ArticlePassage.text)
        wanted = func.websearch_to_tsquery(_ENGLISH, query)
        rank = func.ts_rank(document, wanted, type_=Float)
        statement = apply_filters(
            select(
                ArticlePassage.url_hash,
                Article.published_at,
                ArticlePassage.text,
                rank.label("rank"),
            )
            .join(Article, Article.url_hash == ArticlePassage.url_hash)
            .where(document.op("@@")(wanted)),
            time_from=filters.time_from,
            time_to=filters.time_to,
            theme=filters.theme,
            domain=filters.domain,
            text_filter=None,
            min_negativity=filters.min_negativity,
        )
        statement = statement.order_by(
            rank.desc(),
            Article.published_at.desc(),
            ArticlePassage.url_hash,
            ArticlePassage.idx,
        ).limit(self._passage_candidates)
        with Session(self._engine) as session:
            rows = session.execute(statement).all()
        out: list[Hit] = []
        seen: set[str] = set()
        for url_hash, published_at, passage, _ in rows:
            if url_hash in seen:
                continue
            seen.add(url_hash)
            out.append(Hit(url_hash, published_at, None, passage))
            if len(out) == limit:
                break
        return out

    def summaries(
        self, ids: list[str], include: Sequence[str] = ()
    ) -> dict[str, ArticleSummary]:
        return self._articles.summaries(ids, include)
