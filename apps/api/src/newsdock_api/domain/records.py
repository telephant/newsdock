"""API-facing article shapes (design.md §3 summary form).

Tone (spec tone-in-summary, ADR-0030): the four stored tone numbers sit on
`ArticleSummary` but are `exclude=True`, so every default dump (streams, live feed,
existing callers) is unchanged. A surface that was asked for tone writes it back with
`to_json(include)` or `dump_page`.

Events (spec events-mentions, ADR-0033) follow the same rule: `events` is `exclude=True`
and written only when `include` names it (an empty list when the article has none).
`ArticleDetail` always carries them.
"""

from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventActor(BaseModel):
    """One side of an event; every part may be missing in the GDELT data."""

    code: str | None = None
    name: str | None = None
    country: str | None = None
    type: str | None = None


class EventLocation(BaseModel):
    name: str | None = None
    country: str | None = None
    adm1: str | None = None
    lat: float | None = None
    lon: float | None = None


class EventOut(BaseModel):
    """A GDELT event an article is mentioned in (curated fields, D-2).

    `num_mentions` is GDELT's own count; `mention_count` is the mention rows we stored.
    """

    event_id: int
    date: date_type
    cameo_code: str
    cameo_root: str | None
    goldstein: float | None
    quad_class: int | None
    num_mentions: int
    num_sources: int
    avg_tone: float | None
    actor1: EventActor
    actor2: EventActor
    location: EventLocation | None
    source_url: str
    mention_count: int


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
    events: list[EventOut] | None = Field(default=None, exclude=True)
    body: str | None = Field(default=None, exclude=True)  # spec body-extraction

    def to_json(self, include: Sequence[str] = ()) -> dict[str, Any]:
        """The default JSON plus the requested fields: tone numbers (null when the
        article has none) and `events` (a list, empty when it has none). `include`
        holds names already checked by `parse_include`."""
        out = self.model_dump(mode="json")
        for name in include:
            if name == "events":
                out[name] = [e.model_dump(mode="json") for e in self.events or []]
            else:
                out[name] = getattr(self, name)
        return out


class SemanticHit(ArticleSummary):
    """A `semantic_search` result: the summary plus how it was found.

    `score` is the cosine similarity in `vector` mode and the fused (reciprocal-rank)
    score in `hybrid` mode; `matched_by` lists the legs that returned the article.
    """

    score: float
    matched_by: list[str]
    # the best matching passage of the page text; written by `dump_page` only when the
    # scope searched the text, so the default (titles) payload stays as it was
    passage: str | None = Field(default=None, exclude=True)


class SemanticResult(BaseModel):
    articles: list[SemanticHit]
    mode: str
    degraded: bool  # hybrid fell back to the keyword leg because embedding failed
    scope: str = Field(default="titles", exclude=True)  # titles | body | all


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
    events: list[EventOut] = []  # events it is mentioned in, at most the API's cap
    # spec body-extraction AC-9: the page text (null unless status is `ok`) and why
    body: str | None = None
    body_status: str = "none"  # ok | pending | a failure status | none (no row)


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
    """Documentation only: the schema of `GET /api/articles` before events."""

    articles: list[ArticleSummaryTone]
    next_before: str | None


class ArticleSummaryEvents(ArticleSummaryTone):
    """Documentation only (ADR-0030, ADR-0033): the feed article as it looks when tone
    and `events` are asked for. `events` is an ordinary optional field here so the
    OpenAPI schema shows it; no handler builds it."""

    events: list[EventOut] | None = None
    body: str | None = None  # when `body` is asked for (spec body-extraction)


class FeedPageEvents(BaseModel):
    """Documentation only: the schema of `GET /api/articles`."""

    articles: list[ArticleSummaryEvents]
    next_before: str | None


def dump_page(
    page: NewArticlesPage | FeedPage | SemanticResult, include: Sequence[str] = ()
) -> dict[str, Any]:
    """A page as JSON with the requested tone fields on every article.

    Key order follows the models (`articles` first); the other keys are untouched."""
    out: dict[str, Any] = {"articles": [a.to_json(include) for a in page.articles]}
    if isinstance(page, SemanticResult) and page.scope != "titles":
        for item, hit in zip(out["articles"], page.articles, strict=True):
            item["passage"] = hit.passage
    out.update(page.model_dump(mode="json", exclude={"articles"}))
    return out


class HealthStatus(BaseModel):
    db: bool
    last_published_slot: str | None
    kafka: bool
