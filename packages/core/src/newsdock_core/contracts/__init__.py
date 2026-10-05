"""Kafka message contracts shared by all apps (design.md §3)."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

MAX_DLQ_LINE_CHARS = 2048


class DlqReason(StrEnum):
    """Reasons on `gkg.dlq` — fixed names, do not rename (CLAUDE.md)."""

    missing_url = "missing_url"
    missing_title = "missing_title"
    bad_column_count = "bad_column_count"
    bad_field = "bad_field"


class RawMessage(BaseModel):
    """Value on `gkg.raw`, keyed `<slot>:<row_no>`; `line` is the untouched TSV row."""

    slot: str
    row_no: int
    line: str


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


class DlqMessage(BaseModel):
    """Value on `gkg.dlq`, keyed `<slot>:<row_no>`; `line` capped at 2 KB."""

    reason: DlqReason
    slot: str
    row_no: int
    line: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("line", mode="before")
    @classmethod
    def _truncate_line(cls, v: str) -> str:
        return v[:MAX_DLQ_LINE_CHARS]
