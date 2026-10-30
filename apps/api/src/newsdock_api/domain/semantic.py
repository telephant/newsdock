"""Semantic search over the two legs (spec semantic-search AC-6..AC-10, design C-37).

Pure: the database and Ollama are ports implemented in `adapters/`. `vector` mode
returns the nearest titles by cosine similarity; `hybrid` (the default) fuses that
leg with a full-text keyword leg by reciprocal rank (`ranking.fuse`). Both legs
take the same filters. If the query cannot be embedded, `vector` mode fails with
`EmbeddingUnavailable` and `hybrid` falls back to the keyword leg, flagged degraded.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from newsdock_api.domain.ranking import Ranked, fuse
from newsdock_api.domain.records import ArticleSummary, SemanticHit, SemanticResult

MODES = ("vector", "hybrid")


class InvalidQuery(Exception):
    """Empty or over-long query, or an unknown mode (MCP error `invalid_query`)."""


class EmbeddingUnavailable(Exception):
    """The query could not be embedded (MCP error `embedding_unavailable`)."""


@dataclass(frozen=True)
class SearchFilters:
    """Filters shared by both legs; the same semantics as `search_articles`."""

    time_from: datetime | None = None
    time_to: datetime | None = None
    theme: str | None = None  # exact, or a trailing `*` for a prefix
    domain: str | None = None


@dataclass(frozen=True)
class Hit:
    """One article returned by a leg; `similarity` is set by the vector leg only."""

    id: str
    published_at: datetime
    similarity: float | None = None


class SemanticRepo(Protocol):
    def vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        """Nearest embedded articles of `model`, best first."""
        ...

    def keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        """Full-text matches on the title, best first."""
        ...

    def summaries(self, ids: list[str]) -> dict[str, ArticleSummary]: ...


class QueryEmbedder(Protocol):
    def embed_query(self, query: str) -> list[float]:
        """The query's vector, or raise EmbeddingUnavailable."""
        ...


class SemanticService:
    def __init__(
        self,
        repo: SemanticRepo,
        embedder: QueryEmbedder,
        *,
        model: str,
        candidates: int,
        rrf_k: int,
        max_query_length: int,
        default_limit: int,
        max_limit: int,
    ) -> None:
        self._repo = repo
        self._embedder = embedder
        self._model = model
        self._candidates = candidates
        self._rrf_k = rrf_k
        self._max_query_length = max_query_length
        self._default_limit = default_limit
        self._max_limit = max_limit

    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        theme: str | None = None,
        domain: str | None = None,
        limit: int | None = None,
    ) -> SemanticResult:
        text = query.strip()
        if not text:
            raise InvalidQuery("query is empty")
        if len(text) > self._max_query_length:
            raise InvalidQuery(f"query is longer than {self._max_query_length}")
        if mode not in MODES:
            raise InvalidQuery("mode must be 'vector' or 'hybrid'")
        size = (
            self._default_limit
            if limit is None
            else max(1, min(limit, self._max_limit))
        )
        depth = max(self._candidates, size)  # candidates per leg
        filters = SearchFilters(time_from, time_to, theme, domain)

        vector_hits: list[Hit] = []
        degraded = False
        try:
            vector = self._embedder.embed_query(text)
            vector_hits = self._repo.vector_leg(
                vector=vector, model=self._model, filters=filters, limit=depth
            )
        except EmbeddingUnavailable:
            if mode == "vector":
                raise
            degraded = True

        if mode == "vector":
            scored = [
                (h.id, h.similarity or 0.0, ["vector"]) for h in vector_hits[:size]
            ]
        else:
            keyword_hits = self._repo.keyword_leg(
                query=text, filters=filters, limit=depth
            )
            legs = {"keyword": [Ranked(h.id, h.published_at) for h in keyword_hits]}
            if not degraded:
                legs = {
                    "vector": [Ranked(h.id, h.published_at) for h in vector_hits],
                    **legs,
                }
            fused = fuse(legs, k=self._rrf_k)[:size]
            scored = [(f.id, f.score, list(f.matched_by)) for f in fused]

        summaries = self._repo.summaries([s[0] for s in scored])
        articles = [
            SemanticHit.model_validate(
                {**dict(summaries[i]), "score": score, "matched_by": matched}
            )
            for i, score, matched in scored
            if i in summaries  # a row removed by retention between the legs and now
        ]
        return SemanticResult(articles=articles, mode=mode, degraded=degraded)
