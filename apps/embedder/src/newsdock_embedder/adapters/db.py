"""Postgres access (role: embedder_rw): read unembedded rows, write two columns.

The queue is "rows with no vector yet", served by the partial index
`ix_articles_unembedded (seq DESC) WHERE embedding IS NULL` (migration 0009), so
picking the next batch costs the same with 60 or 600,000 rows already embedded. A scan
over `ORDER BY seq DESC` with a "not embedded" filter had to walk past every embedded
row (measured: 78 ms per idle poll at 67,000 rows).
"""

from newsdock_db.models import Article
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from newsdock_embedder.domain.loop import DbUnavailable, Row


class SqlEmbedRepo:
    """Implements the worker's EmbedRepo port with parameterized ORM statements."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def invalidate_stale(self, model: str) -> int:
        """Clear vectors of any other model so they re-enter the queue (AC-11)."""
        statement = (
            update(Article)
            .where(
                Article.embedding.is_not(None),
                Article.embedding_model.is_distinct_from(model),
            )
            .values(embedding=None, embedding_model=None)
        )
        try:
            with Session(self._engine) as session:
                result = session.execute(statement)
                session.commit()
                return int(getattr(result, "rowcount", 0) or 0)
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc

    def next_batch(self, limit: int, exclude: frozenset[str]) -> list[Row]:
        statement = select(Article.url_hash, Article.title).where(
            Article.embedding.is_(None)
        )
        if exclude:
            statement = statement.where(Article.url_hash.not_in(exclude))
        statement = statement.order_by(Article.seq.desc()).limit(limit)
        try:
            with Session(self._engine) as session:
                return [Row(r[0], r[1]) for r in session.execute(statement).all()]
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc

    def store(self, url_hash: str, vector: list[float], model: str) -> bool:
        """Fill the empty slot; False when the row got a vector meanwhile."""
        statement = (
            update(Article)
            .where(Article.url_hash == url_hash, Article.embedding.is_(None))
            .values(embedding=vector, embedding_model=model)
        )
        try:
            with Session(self._engine) as session:
                result = session.execute(statement)
                session.commit()
                return bool(getattr(result, "rowcount", 0))
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc
