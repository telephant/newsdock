"""Semantic search over the two legs (spec semantic-search AC-6..AC-10, design C-37).

Pure: the database and Ollama are ports implemented in `adapters/`. `vector` mode
returns the nearest titles by cosine similarity; `hybrid` (the default) fuses that
leg with a full-text keyword leg by reciprocal rank (`ranking.fuse`). Both legs
take the same filters. If the query cannot be embedded, `vector` mode fails with
`EmbeddingUnavailable` and `hybrid` falls back to the keyword leg, flagged degraded.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from newsdock_api.domain.ranking import Ranked, fuse
from newsdock_api.domain.records import ArticleSummary, SemanticHit, SemanticResult

MODES = ("vector", "hybrid")
# what is searched (spec body-extraction D-5): titles only, page text only, or both
SCOPES = ("titles", "body", "all")
# the order of `matched_by` when an article is found by several legs
_LEG_ORDER = ("vector", "keyword", "body_vector", "body_keyword")


class InvalidQuery(Exception):
    """Empty or over-long query, or an unknown mode (MCP error `invalid_query`)."""


class InvalidScope(Exception):
    """An unknown `scope` (MCP error `invalid_scope`)."""


class EmbeddingUnavailable(Exception):
    """The query could not be embedded (MCP error `embedding_unavailable`)."""


@dataclass(frozen=True)
class SearchFilters:
    """Filters shared by both legs; the same semantics as `search_articles`."""

    time_from: datetime | None = None
    time_to: datetime | None = None
    theme: str | None = None  # exact, or a trailing `*` for a prefix
    domain: str | None = None
    min_negativity: float | None = None  # tone_neg at or above; checked by the caller


@dataclass(frozen=True)
class Hit:
    """One article returned by a leg; `similarity` is set by the vector leg only."""

    id: str
    published_at: datetime
    similarity: float | None = None
    passage: str | None = None  # the best passage of the article; passage legs only


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

    def summaries(
        self, ids: list[str], include: Sequence[str] = ()
    ) -> dict[str, ArticleSummary]: ...


class PassageRepo(Protocol):
    """The two legs over the embedded page text (spec body-extraction, ADR-0037)."""

    def passage_vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        """Articles by their nearest passage, best first, one hit per article."""
        ...

    def passage_keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        """Articles by a full-text match on a passage, best first."""
        ...


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
        default_scope: str = "titles",
        passages: PassageRepo | None = None,
    ) -> None:
        self._passages = passages
        self._default_scope = default_scope
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
        min_negativity: float | None = None,
        include: Sequence[str] = (),
        scope: str | None = None,
    ) -> SemanticResult:
        text = query.strip()
        if not text:
            raise InvalidQuery("query is empty")
        if len(text) > self._max_query_length:
            raise InvalidQuery(f"query is longer than {self._max_query_length}")
        if mode not in MODES:
            raise InvalidQuery("mode must be 'vector' or 'hybrid'")
        chosen = self._default_scope if scope is None else scope
        if chosen not in SCOPES:
            raise InvalidScope(f"scope must be one of {', '.join(SCOPES)}")
        use_titles = chosen in ("titles", "all")
        use_body = chosen in ("body", "all")
        if use_body and self._passages is None:
            raise InvalidScope("searching page text is not available")
        size = (
            self._default_limit
            if limit is None
            else max(1, min(limit, self._max_limit))
        )
        depth = max(self._candidates, size)  # candidates per leg
        filters = SearchFilters(time_from, time_to, theme, domain, min_negativity)

        hits: dict[str, list[Hit]] = {}
        degraded = False
        try:
            vector = self._embedder.embed_query(text)  # once, shared by the legs
            if use_titles:
                hits["vector"] = self._repo.vector_leg(
                    vector=vector, model=self._model, filters=filters, limit=depth
                )
            if use_body and self._passages is not None:
                hits["body_vector"] = self._passages.passage_vector_leg(
                    vector=vector, model=self._model, filters=filters, limit=depth
                )
        except EmbeddingUnavailable:
            if mode == "vector":
                raise
            degraded = True

        if mode == "hybrid":
            if use_titles:
                hits["keyword"] = self._repo.keyword_leg(
                    query=text, filters=filters, limit=depth
                )
            if use_body and self._passages is not None:
                hits["body_keyword"] = self._passages.passage_keyword_leg(
                    query=text, filters=filters, limit=depth
                )
        names = [n for n in _LEG_ORDER if n in hits]

        if mode == "vector" and len(names) == 1:
            # one leg: the cosine similarity itself is the score
            scored = [(h.id, h.similarity or 0.0, names) for h in hits[names[0]][:size]]
        else:
            fused = fuse(
                {n: [Ranked(h.id, h.published_at) for h in hits[n]] for n in names},
                k=self._rrf_k,
            )[:size]
            scored = [(f.id, f.score, list(f.matched_by)) for f in fused]

        passage_of = _best_passages(hits)
        summaries = self._repo.summaries([s[0] for s in scored], include)
        articles = [
            SemanticHit.model_validate(
                {
                    **dict(summaries[i]),
                    "score": score,
                    "matched_by": matched,
                    "passage": passage_of.get(i),
                }
            )
            for i, score, matched in scored
            if i in summaries  # a row removed by retention between the legs and now
        ]
        return SemanticResult(
            articles=articles, mode=mode, degraded=degraded, scope=chosen
        )


def _best_passages(hits: dict[str, list[Hit]]) -> dict[str, str]:
    """Per article, the passage from the passage leg where it ranks highest.

    A tie goes to the vector leg (it is looked at first); a hit without a passage
    never wins."""
    best: dict[str, tuple[int, str]] = {}
    for name in ("body_vector", "body_keyword"):
        seen: set[str] = set()
        rank = 0
        for h in hits.get(name, []):
            if h.id in seen:
                continue
            seen.add(h.id)
            rank += 1
            if h.passage is not None and (h.id not in best or rank < best[h.id][0]):
                best[h.id] = (rank, h.passage)
    return {i: passage for i, (_, passage) in best.items()}
