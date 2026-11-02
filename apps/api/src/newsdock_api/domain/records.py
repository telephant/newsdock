"""API-facing article shapes (design.md §3 summary form).

Tone (spec tone-in-summary, ADR-0030): the four stored tone numbers sit on
`ArticleSummary` but are `exclude=True`, so every default dump (streams, live feed,
existing callers) is unchanged. A surface that was asked for tone writes it back with
`to_json(include)` or `dump_page`.
"""

from collections.abc import Sequence
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
    source_count: int = 1  # copies of this story; pre-feature rows read as 1 (M2a)
    # Filled by the repo only for the names a caller asked for; never in a default dump.
    tone: float | None = Field(default=None, exclude=True)
    tone_pos: float | None = Field(default=None, exclude=True)
    tone_neg: float | None = Field(default=None, exclude=True)
    tone_polarity: float | None = Field(default=None, exclude=True)

    def to_json(self, include: Sequence[str] = ()) -> dict[str, Any]:
        """The default JSON plus the requested tone fields (null when the article
        has no value). `include` holds names already checked by `parse_include`."""
        out = self.model_dump(mode="json")
        for name in include:
            out[name] = getattr(self, name)
        return out


class SemanticHit(ArticleSummary):
    """A `semantic_search` result: the summary plus how it was found.

    `score` is the cosine similarity in `vector` mode and the fused (reciprocal-rank)
    score in `hybrid` mode; `matched_by` lists the legs that returned the article.
    """

    score: float
    matched_by: list[str]


class SemanticResult(BaseModel):
    articles: list[SemanticHit]
    mode: str
    degraded: bool  # hybrid fell back to the keyword leg because embedding failed


class SourceRecord(BaseModel):
    """One copy (URL) that carried the story (M2a)."""

    url: str
    domain: str | None
    published_at: datetime


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
    tone_pos: float | None = None
    tone_neg: float | None = None
    tone_polarity: float | None = None
    word_count: int | None
    analyses: list[AnalysisRecord]
    sources: list[SourceRecord]  # ordered by published_at (M2a)
    source_count: int


class NewArticlesPage(BaseModel):
    articles: list[ArticleSummary]
    next_cursor: str


class FeedPage(BaseModel):
    """REST /api/articles response (keyset pagination via next_before)."""

    articles: list[ArticleSummary]
    next_before: str | None


class ArticleSummaryTone(ArticleSummary):
    """Documentation only (ADR-0030): the feed article as it looks when tone is asked
    for. It redeclares the four fields as ordinary optional ones so the OpenAPI schema
    shows them; no handler builds it."""

    tone: float | None = None
    tone_pos: float | None = None
    tone_neg: float | None = None
    tone_polarity: float | None = None


class FeedPageTone(BaseModel):
    """Documentation only: the schema of `GET /api/articles`."""

    articles: list[ArticleSummaryTone]
    next_before: str | None


def dump_page(
    page: NewArticlesPage | FeedPage | SemanticResult, include: Sequence[str] = ()
) -> dict[str, Any]:
    """A page as JSON with the requested tone fields on every article.

    Key order follows the models (`articles` first); the other keys are untouched."""
    out: dict[str, Any] = {"articles": [a.to_json(include) for a in page.articles]}
    out.update(page.model_dump(mode="json", exclude={"articles"}))
    return out


class HealthStatus(BaseModel):
    db: bool
    last_published_slot: str | None
    kafka: bool
