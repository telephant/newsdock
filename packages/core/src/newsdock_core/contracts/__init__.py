"""Kafka message contracts shared by all apps (design.md §3)."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_DLQ_LINE_CHARS = 2048

Kind = Literal["gkg", "events", "mentions"]
"""Which GDELT file a raw line came from (ADR-0032); messages without it mean GKG."""


class DlqReason(StrEnum):
    """Reasons on `gkg.dlq`: fixed names, do not rename (CLAUDE.md); only extended."""

    missing_url = "missing_url"
    missing_title = "missing_title"
    missing_event_id = "missing_event_id"
    bad_column_count = "bad_column_count"
    bad_field = "bad_field"


class RawMessage(BaseModel):
    """Value on `gkg.raw`, keyed `<slot>:<row_no>` (`<slot>:<kind>:<row_no>` otherwise).

    `line` is the untouched TSV row; `kind` defaults to `gkg` (old messages stay valid).
    """

    slot: str
    row_no: int
    line: str
    kind: Kind = "gkg"


class Tone(BaseModel):
    """Subset of GKG V2Tone kept by the MVP (col 16: 1st–4th and 7th numbers)."""

    tone: float
    positive: float
    negative: float
    polarity: float
    word_count: int


class CleanArticle(BaseModel):
    """Value on `gkg.clean`, keyed `url_hash`."""

    url_hash: str
    gkg_record_id: str
    slot: str
    url: str
    title: str
    domain: str | None
    published_at: datetime
    themes: list[str]
    persons: list[str]
    orgs: list[str]
    tone: Tone


class Actor(BaseModel):
    """One side of an event; every part is optional (GDELT leaves many empty)."""

    code: str | None = None
    name: str | None = None
    country: str | None = None
    type1: str | None = None


class Geo(BaseModel):
    """Where the action took place (Events `ActionGeo_*`)."""

    name: str | None = None
    country: str | None = None
    adm1: str | None = None
    lat: float | None = None
    lon: float | None = None


class CleanEvent(BaseModel):
    """Value on `events.clean`, keyed `event_id` (curated subset of 61 columns, D-2)."""

    event_id: int
    event_date: date
    actor1: Actor
    actor2: Actor
    is_root: bool
    cameo_code: str
    cameo_base: str | None
    cameo_root: str | None
    quad_class: int | None
    goldstein: float | None
    num_mentions: int
    num_sources: int
    num_articles: int
    avg_tone: float | None
    geo: Geo | None
    date_added: datetime
    source_url: str
    source_url_hash: str


class CleanMention(BaseModel):
    """Value on `mentions.clean`, keyed `<event_id>:<url_hash>`."""

    event_id: int
    url: str
    url_hash: str
    source_name: str | None
    mention_time: datetime
    confidence: int | None


class DlqMessage(BaseModel):
    """Value on `gkg.dlq`, keyed `<slot>:<row_no>`; `line` capped at 2 KB."""

    reason: DlqReason
    slot: str
    row_no: int
    line: str
    kind: Kind = "gkg"
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("line", mode="before")
    @classmethod
    def _truncate_line(cls, v: str) -> str:
        return v[:MAX_DLQ_LINE_CHARS]
