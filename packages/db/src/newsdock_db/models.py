"""M1 tables as SQLAlchemy 2.0 declarative mapped classes (ADR-0008, R-14).

The SQL contract is docs/specs/mvp/design-detail.md §1; migrations are
hand-written (infra/migrations/versions/0002_articles.py) and TC-34 proves
they do not drift from these models. Apps use them only in `adapters/`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REAL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from newsdock_db.metadata import metadata


class Base(DeclarativeBase):
    metadata = metadata


class Article(Base):
    """One article per normalized URL; `url_hash` is the public article id."""

    __tablename__ = "articles"

    url_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    # insert order, cursor basis; identity = bigserial semantics
    seq: Mapped[int] = mapped_column(
        BigInteger, Identity(), unique=True, nullable=False
    )
    gkg_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    slot: Mapped[str] = mapped_column(Text, nullable=False)  # YYYYMMDDHHMMSS
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    themes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    persons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    orgs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    tone: Mapped[float | None] = mapped_column(REAL, nullable=True)
    tone_pos: Mapped[float | None] = mapped_column(REAL, nullable=True)
    tone_neg: Mapped[float | None] = mapped_column(REAL, nullable=True)
    tone_polarity: Mapped[float | None] = mapped_column(REAL, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_ingested_at", "ingested_at"),
        Index("ix_articles_themes", "themes", postgresql_using="gin"),
        Index("ix_articles_domain", "domain"),
    )


class Analysis(Base):
    """Agent write-back; resubmission replaces (latest wins) via the PK."""

    __tablename__ = "analyses"

    article_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("articles.url_hash", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_name: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class IngestSlot(Base):
    """Slot state machine: pending → published, or failed after 4 attempts."""

    __tablename__ = "ingest_slot"

    slot: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
