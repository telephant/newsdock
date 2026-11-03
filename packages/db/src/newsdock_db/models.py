"""M1 tables as SQLAlchemy 2.0 declarative mapped classes (ADR-0008, R-14).

The SQL contract is docs/specs/mvp/design-detail.md §1; migrations are
hand-written (infra/migrations/versions/0002_articles.py) and TC-34 proves
they do not drift from these models. Apps use them only in `adapters/`.
"""

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import HALFVEC, Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    Uuid,
    text,
)
from sqlalchemy import text as sql_text  # `text` is also a column name below
from sqlalchemy.dialects.postgresql import ARRAY, DOUBLE_PRECISION, JSONB, REAL
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


class PasswordReset(Base):
    """The open password reset code of a user (M2f forgot-password, ADR-0026).

    One row per user: a newer request replaces the older code. `code_hash` is a keyed
    HMAC of the six-digit code, never the code.
    """

    __tablename__ = "password_resets"

    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("ix_password_resets_expires_at", "expires_at"),)


class Event(Base):
    """A GDELT event (M3c events-mentions, ADR-0033): curated subset of the 61 columns.

    No foreign keys: the three files of a slot arrive in any order. `source_url_hash`
    is the `url_hash` of the article the event was coded from.
    """

    __tablename__ = "events"

    event_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_root: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    actor1_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor1_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor1_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor1_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor2_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor2_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor2_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor2_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    cameo_code: Mapped[str] = mapped_column(Text, nullable=False)
    cameo_base: Mapped[str | None] = mapped_column(Text, nullable=True)
    cameo_root: Mapped[str | None] = mapped_column(Text, nullable=True)
    quad_class: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    goldstein: Mapped[float | None] = mapped_column(REAL, nullable=True)
    num_mentions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    num_sources: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    num_articles: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    avg_tone: Mapped[float | None] = mapped_column(REAL, nullable=True)
    geo_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo_adm1: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo_lat: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    geo_lon: Mapped[float | None] = mapped_column(DOUBLE_PRECISION, nullable=True)
    date_added: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_events_ingested_at", "ingested_at"),
        Index("ix_events_source_url_hash", "source_url_hash"),
    )


class Mention(Base):
    """One article mentioning one event (M3c events-mentions, ADR-0033).

    Key `(event_id, url_hash)`; `url_hash` joins to `articles.url_hash` with no foreign
    key, and `event_id` to `events.event_id` the same way.
    """

    __tablename__ = "mentions"

    event_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    url_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    mention_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_mentions_url_hash", "url_hash", "event_id"),
        Index("ix_mentions_ingested_at", "ingested_at"),
    )


class IngestFile(Base):
    """Fetch state of the Events or Mentions file of a slot (ADR-0032).

    Same lifecycle as `IngestSlot` (pending, published, failed); GKG stays in
    `ingest_slot`, so a missing file never blocks it.
    """

    __tablename__ = "ingest_file"

    slot: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (CheckConstraint("kind IN ('events', 'mentions')", name="kind"),)


class ArticleBody(Base):
    """The fetched text of one canonical article and the queue row for it (M3d
    body-extraction, ADR-0036).

    The extractor creates a `pending` row for each new article (discovery by `seq`),
    then fills `status`, `text` and the retry fields. Deleted with the article.
    """

    __tablename__ = "article_bodies"

    url_hash: Mapped[str] = mapped_column(
        Text,
        ForeignKey("articles.url_hash", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)  # = articles.seq
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sql_text("'pending'")
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=sql_text("0")
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ok', 'blocked_robots', 'blocked_address', "
            "'http_error', 'not_html', 'too_large', 'no_text', 'failed')",
            name="status",
        ),
        # discovery cursor: max(seq)
        Index("ix_article_bodies_seq", "seq"),
        # the extractor's queue: rows still waiting (read newest first, backwards)
        Index(
            "ix_article_bodies_pending",
            "seq",
            postgresql_where=sql_text("status = 'pending'"),
        ),
    )


class ArticlePassage(Base):
    """A piece of a body (about 1,000 characters) with its vector (ADR-0036).

    The extractor writes the rows with no vector; the embedder fills `embedding` and
    `embedding_model`. `halfvec(768)` halves the storage of `vector(768)`.
    """

    __tablename__ = "article_passages"

    url_hash: Mapped[str] = mapped_column(
        Text,
        ForeignKey("articles.url_hash", ondelete="CASCADE"),
        primary_key=True,
    )
    idx: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(768), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_article_passages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
        Index(
            "ix_article_passages_text_fts",
            sql_text("to_tsvector('english', text)"),
            postgresql_using="gin",
        ),
        # the embedder's queue: passages still waiting for a vector
        Index(
            "ix_article_passages_unembedded",
            "url_hash",
            postgresql_where=sql_text("embedding IS NULL"),
        ),
    )
