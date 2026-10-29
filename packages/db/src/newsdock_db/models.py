"""M1 tables as SQLAlchemy 2.0 declarative mapped classes (ADR-0008, R-14).

The SQL contract is docs/specs/mvp/design-detail.md §1; migrations are
hand-written (infra/migrations/versions/0002_articles.py) and TC-34 proves
they do not drift from these models. Apps use them only in `adapters/`.
"""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    Uuid,
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
    # grouping key (ADR-0012); NULL = pre-feature row that never groups (D-4)
    story_key: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # semantic-search (M3, migration 0008): filled by the embedder worker, never by
    # the sink; NULL = not embedded yet. Canonical rows only (ADR-0024, ADR-0025).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_ingested_at", "ingested_at"),
        Index("ix_articles_themes", "themes", postgresql_using="gin"),
        Index("ix_articles_domain", "domain"),
        Index("ix_articles_story_key_published_at", "story_key", "published_at"),
        Index(
            "ix_articles_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_articles_title_fts",
            text("to_tsvector('english', title)"),
            postgresql_using="gin",
        ),
        # the embedder's queue: rows still waiting for a vector (migration 0009)
        Index(
            "ix_articles_unembedded", "seq", postgresql_where=text("embedding IS NULL")
        ),
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


class ArticleSource(Base):
    """One copy (URL) of a story; the canonical's own URL is also a source."""

    __tablename__ = "article_sources"

    url_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    article_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("articles.url_hash", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    slot: Mapped[str] = mapped_column(Text, nullable=False)
    gkg_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("ix_article_sources_article_id", "article_id"),)


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


class Agent(Base):
    """A registered API client (M2 agent-platform); `name` is unique and immutable."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )  # active | disabled
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # The creating user (agent-ownership, ADR-0023); NULL = no owner: CLI/admin-token
    # agents, agents from before 0007, and agents whose creator was deleted.
    owner_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class ApiKey(Base):
    """Only the public prefix and sha256(secret) are stored (ADR-0016)."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    prefix: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_api_keys_agent_id", "agent_id"),)


class AgentCursor(Base):
    """Per-agent read position: the highest acknowledged `articles.seq` (ADR-0017)."""

    __tablename__ = "agent_cursors"

    agent_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Subscription(Base):
    """An agent's saved filter (M2 push-delivery); `filter` holds only given fields."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    filter: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("ix_subscriptions_agent_id", "agent_id"),)


class User(Base):
    """A human account (M2 ui-login); `email` is stored trimmed and lower-cased."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)  # argon2id PHC
    role: Mapped[str] = mapped_column(Text, nullable=False)  # owner | admin | viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'viewer')", name="role"),
    )


class UserSession(Base):
    """A login session; only sha256 of the cookie value is stored (ADR-0020)."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )
