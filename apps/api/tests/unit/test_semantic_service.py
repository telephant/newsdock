"""TC-20 (AC-6) and the search rules of AC-6, AC-8, AC-9, AC-10 at service level."""

from datetime import UTC, datetime, timedelta

import pytest
from newsdock_api.domain.records import ArticleSummary
from newsdock_api.domain.semantic import (
    EmbeddingUnavailable,
    Hit,
    InvalidQuery,
    SearchFilters,
    SemanticService,
)

T0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
MODEL = "m1"


def hit(article_id: str, similarity: float | None = None, minutes: int = 0) -> Hit:
    return Hit(article_id, T0 - timedelta(minutes=minutes), similarity)


class FakeRepo:
    def __init__(self) -> None:
        self.vector: list[Hit] = []
        self.keyword: list[Hit] = []
        self.vector_calls: list[dict[str, object]] = []
        self.keyword_calls: list[dict[str, object]] = []

    def vector_leg(
        self,
        *,
        vector: list[float],
        model: str,
        filters: SearchFilters,
        limit: int,
    ) -> list[Hit]:
        self.vector_calls.append(
            {"vector": vector, "model": model, "filters": filters, "limit": limit}
        )
        return list(self.vector)

    def keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        self.keyword_calls.append({"query": query, "filters": filters, "limit": limit})
        return list(self.keyword)

    def summaries(self, ids: list[str]) -> dict[str, ArticleSummary]:
        return {
            i: ArticleSummary(
                article_id=i,
                title=f"title {i}",
                url=f"https://e.com/{i}",
                domain="e.com",
                published_at=T0,
                themes=[],
                seq=1,
            )
            for i in ids
        }


class FakeEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.down = False

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        if self.down:
            raise EmbeddingUnavailable("ollama down")
        return [0.5, 0.5]


def service(
    repo: FakeRepo,
    embedder: FakeEmbedder,
    *,
    default: int = 20,
    maximum: int = 100,
    max_len: int = 500,
) -> SemanticService:
    return SemanticService(
        repo,
        embedder,
        model=MODEL,
        candidates=50,
        rrf_k=60,
        max_query_length=max_len,
        default_limit=default,
        max_limit=maximum,
    )


def ids(result: object) -> list[str]:
    return [a.article_id for a in result.articles]  # type: ignore[attr-defined]


# TC-20: bad input is refused before any embedding call
@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_an_empty_query_is_invalid(query: str) -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    with pytest.raises(InvalidQuery, match="query"):
        service(repo, embedder).search(query)
    assert embedder.queries == [] and repo.vector_calls == []


def test_an_over_long_query_is_invalid() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    with pytest.raises(InvalidQuery, match="query"):
        service(repo, embedder, max_len=10).search("x" * 11)
    assert embedder.queries == []


def test_an_unknown_mode_is_invalid() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    with pytest.raises(InvalidQuery, match="mode"):
        service(repo, embedder).search("rates", mode="keyword")
    assert embedder.queries == []


# AC-6: vector mode keeps the repo order and reports similarity as the score
def test_vector_mode_returns_similarity_as_score_in_order() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    repo.vector = [hit("a", 0.9), hit("b", 0.4), hit("c", -0.1)]
    result = service(repo, embedder).search("rates", mode="vector")
    assert (result.mode, result.degraded) == ("vector", False)
    assert ids(result) == ["a", "b", "c"]
    assert [a.score for a in result.articles] == [0.9, 0.4, -0.1]
    assert all(a.matched_by == ["vector"] for a in result.articles)
    assert repo.keyword_calls == []  # vector mode never runs the keyword leg


def test_the_query_is_stripped_and_the_model_and_candidates_are_passed() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    service(repo, embedder).search("  interest rates  ", mode="hybrid")
    assert embedder.queries == ["interest rates"]
    assert repo.vector_calls[0]["model"] == MODEL
    assert repo.vector_calls[0]["limit"] == 50
    assert repo.keyword_calls[0]["query"] == "interest rates"
    assert repo.keyword_calls[0]["limit"] == 50


# AC-8: hybrid fuses both legs
def test_hybrid_ranks_an_article_found_by_both_legs_first() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    repo.vector = [hit("b", 0.9), hit("a", 0.8)]
    repo.keyword = [hit("c"), hit("a")]
    result = service(repo, embedder).search("rates")  # hybrid is the default
    assert ids(result)[0] == "a"
    assert set(ids(result)) == {"a", "b", "c"}
    matched = {a.article_id: a.matched_by for a in result.articles}
    assert matched == {"a": ["vector", "keyword"], "b": ["vector"], "c": ["keyword"]}
    assert result.mode == "hybrid" and result.degraded is False


def test_hybrid_scores_are_the_fused_scores_not_similarities() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    repo.vector = [hit("a", 0.99)]
    result = service(repo, embedder).search("rates")
    assert result.articles[0].score == pytest.approx(1 / 61)


# AC-9: the same filters reach both legs
def test_filters_reach_both_legs() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    service(repo, embedder).search(
        "rates", theme="ECON_*", domain="e.com", time_from=T0, time_to=T0
    )
    expected = SearchFilters(time_from=T0, time_to=T0, theme="ECON_*", domain="e.com")
    assert repo.vector_calls[0]["filters"] == expected
    assert repo.keyword_calls[0]["filters"] == expected


# limit: default and clamp like search_articles
def test_limit_defaults_and_is_clamped() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    repo.vector = [hit(f"a{i}", 1.0 - i / 1000) for i in range(30)]
    svc = service(repo, embedder, default=5, maximum=8)
    assert len(svc.search("q", mode="vector").articles) == 5
    assert len(svc.search("q", mode="vector", limit=7).articles) == 7
    assert len(svc.search("q", mode="vector", limit=500).articles) == 8
    assert len(svc.search("q", mode="vector", limit=0).articles) == 1


# AC-10: Ollama down
def test_vector_mode_raises_when_the_embedder_is_down() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    embedder.down = True
    with pytest.raises(EmbeddingUnavailable):
        service(repo, embedder).search("rates", mode="vector")


def test_hybrid_degrades_to_the_keyword_leg_when_the_embedder_is_down() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    embedder.down = True
    repo.keyword = [hit("k1"), hit("k2")]
    result = service(repo, embedder).search("rates")
    assert result.degraded is True
    assert ids(result) == ["k1", "k2"]
    assert all(a.matched_by == ["keyword"] for a in result.articles)
    assert repo.vector_calls == []


def test_no_embeddings_yet_is_not_degraded() -> None:
    repo, embedder = FakeRepo(), FakeEmbedder()
    repo.keyword = [hit("k1")]  # the vector leg is empty: nothing embedded
    result = service(repo, embedder).search("rates")
    assert result.degraded is False
    assert ids(result) == ["k1"]
    assert service(repo, embedder).search("rates", mode="vector").articles == []
