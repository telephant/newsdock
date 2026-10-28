"""Postgres access (role: embedder_rw): read unembedded rows, write two columns."""

from newsdock_db.models import Article
from sqlalchemy import Engine, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from newsdock_embedder.domain.loop import DbUnavailable, Row


def _needs_embedding(model: str) -> ColumnElement[bool]:
    return or_(
        Article.embedding.is_(None), Article.embedding_model.is_distinct_from(model)
    )


class SqlEmbedRepo:
    """Implements the worker's EmbedRepo port with parameterized ORM statements."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def next_batch(self, model: str, limit: int, exclude: frozenset[str]) -> list[Row]:
        statement = select(Article.url_hash, Article.title).where(
            _needs_embedding(model)
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
        statement = (
            update(Article)
            .where(Article.url_hash == url_hash, _needs_embedding(model))
            .values(embedding=vector, embedding_model=model)
        )
        try:
            with Session(self._engine) as session:
                result = session.execute(statement)
                session.commit()
                return bool(getattr(result, "rowcount", 0))
        except OperationalError as exc:
            raise DbUnavailable(str(exc)) from exc
