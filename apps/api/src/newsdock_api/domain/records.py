"""API-facing article shapes (design.md §3 summary form)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ArticleSummary(BaseModel):
    article_id: str
    title: str
    url: str
    domain: str | None
    published_at: datetime
    themes: list[str]
    seq: int = Field(exclude=True)  # cursor basis; never exposed raw (CLAUDE.md)
    scores: dict[str, float] | None = None  # latest numeric score per agent (REST)


class AnalysisRecord(BaseModel):
    agent_name: str
    payload: dict[str, Any]
    created_at: datetime


class ArticleDetail(BaseModel):
    article_id: str
    title: str
    url: str
    domain: str | None
    published_at: datetime
    ingested_at: datetime
    slot: str
    themes: list[str]
    persons: list[str]
    orgs: list[str]
    tone: float | None
    word_count: int | None
    analyses: list[AnalysisRecord]


class NewArticlesPage(BaseModel):
    articles: list[ArticleSummary]
    next_cursor: str


class FeedPage(BaseModel):
    """REST /api/articles response (keyset pagination via next_before)."""

    articles: list[ArticleSummary]
    next_before: str | None


class HealthStatus(BaseModel):
    db: bool
    last_published_slot: str | None
    kafka: bool
