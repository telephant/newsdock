"""TC-21 (body-extraction AC-12, AC-13, AC-14): scopes at service level."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from newsdock_api.domain.records import ArticleSummary
from newsdock_api.domain.semantic import (
    EmbeddingUnavailable,
    Hit,
    InvalidScope,
    SearchFilters,
    SemanticService,
)

T0 = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)


def hit(
    article_id: str,
    similarity: float | None = None,
    passage: str | None = None,
    minutes: int = 0,
) -> Hit:
    return Hit(article_id, T0 - timedelta(minutes=minutes), similarity, passage)


class FakeRepo:
    def __init__(self) -> None:
        self.legs: dict[str, list[Hit]] = {
            "vector": [], "keyword": [], "body_vector": [], "body_keyword": [],
        }  # fmt: skip
        self.calls: list[str] = []
        self.filters: list[SearchFilters] = []

    def _leg(self, name: str, filters: SearchFilters) -> list[Hit]:
        self.calls.append(name)
        self.filters.append(filters)
        return list(self.legs[name])

    def vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        return self._leg("vector", filters)

    def keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        return self._leg("keyword", filters)

    def passage_vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        return self._leg("body_vector", filters)

    def passage_keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        return self._leg("body_keyword", filters)

    def summaries(
        self, ids: list[str], include: Sequence[str] = ()
    ) -> dict[str, ArticleSummary]:
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
        return [1.0]


def make(
    repo: FakeRepo, embedder: FakeEmbedder, default_scope: str = "titles"
) -> SemanticService:
    return SemanticService(
        repo,
        embedder,
        model="m1",
        candidates=10,
        rrf_k=60,
        max_query_length=500,
        default_limit=10,
        max_limit=50,
        default_scope=default_scope,
        passages=repo,
    )


def test_titles_scope_never_touches_the_passage_legs() -> None:
    repo, emb = FakeRepo(), FakeEmbedder()
    repo.legs["vector"] = [hit("a", 0.9)]
    result = make(repo, emb).search("q")
    assert repo.calls == ["vector", "keyword"]
    assert result.scope == "titles"
    assert result.articles[0].passage is None


def test_an_unknown_scope_is_invalid_scope() -> None:
    with pytest.raises(InvalidScope):
        make(FakeRepo(), FakeEmbedder()).search("q", scope="everything")


def test_the_default_scope_comes_from_the_setting() -> None:
    repo = FakeRepo()
    result = make(repo, FakeEmbedder(), default_scope="all").search("q")
    assert result.scope == "all"
    assert sorted(repo.calls) == ["body_keyword", "body_vector", "keyword", "vector"]


def test_body_scope_hybrid_uses_only_the_passage_legs() -> None:
    repo, emb = FakeRepo(), FakeEmbedder()
    repo.legs["body_vector"] = [hit("a", 0.8, "passage from vector")]
    repo.legs["body_keyword"] = [hit("a", None, "passage from words"), hit("b")]
    result = make(repo, emb).search("q", scope="body")
    assert sorted(repo.calls) == ["body_keyword", "body_vector"]
    assert [a.article_id for a in result.articles] == ["a", "b"]
    assert result.articles[0].matched_by == ["body_vector", "body_keyword"]
    assert result.articles[0].passage == "passage from vector"
    assert result.articles[1].passage is None  # keyword hit that carried no passage


def test_body_scope_vector_mode_scores_by_similarity() -> None:
    repo = FakeRepo()
    repo.legs["body_vector"] = [hit("a", 0.8, "p"), hit("b", 0.5, "q")]
    result = make(repo, FakeEmbedder()).search("q", mode="vector", scope="body")
    assert [(a.article_id, a.score, a.matched_by) for a in result.articles] == [
        ("a", 0.8, ["body_vector"]),
        ("b", 0.5, ["body_vector"]),
    ]
    assert [a.passage for a in result.articles] == ["p", "q"]


def test_all_scope_fuses_four_legs_and_keeps_title_only_hits_without_passage() -> None:
    repo = FakeRepo()
    repo.legs["vector"] = [hit("title-only", 0.9)]
    repo.legs["keyword"] = [hit("title-only")]
    repo.legs["body_vector"] = [hit("text-only", 0.7, "the matching passage")]
    result = make(repo, FakeEmbedder()).search("q", scope="all")
    found = {a.article_id: a for a in result.articles}
    assert set(found) == {"title-only", "text-only"}
    assert found["title-only"].matched_by == ["vector", "keyword"]
    assert found["title-only"].passage is None
    assert found["text-only"].matched_by == ["body_vector"]
    assert found["text-only"].passage == "the matching passage"


def test_the_passage_comes_from_the_leg_where_the_article_ranks_best() -> None:
    repo = FakeRepo()
    repo.legs["body_vector"] = [hit("x", 0.9, "x vec"), hit("a", 0.5, "a vec")]
    repo.legs["body_keyword"] = [hit("a", None, "a words")]
    result = make(repo, FakeEmbedder()).search("q", scope="body")
    found = {a.article_id: a for a in result.articles}
    assert found["a"].passage == "a words"  # first in the keyword leg, second in vector


def test_all_scope_vector_mode_fuses_title_and_passage_vectors() -> None:
    repo = FakeRepo()
    repo.legs["vector"] = [hit("a", 0.9)]
    repo.legs["body_vector"] = [hit("a", 0.6, "p"), hit("b", 0.5, "q")]
    result = make(repo, FakeEmbedder()).search("q", mode="vector", scope="all")
    assert sorted(repo.calls) == ["body_vector", "vector"]
    assert [a.article_id for a in result.articles] == ["a", "b"]
    assert result.articles[0].matched_by == ["vector", "body_vector"]


def test_the_query_is_embedded_once_for_all_vector_legs() -> None:
    emb = FakeEmbedder()
    make(FakeRepo(), emb).search("hello", scope="all")
    assert emb.queries == ["hello"]


def test_the_filters_reach_the_passage_legs() -> None:
    repo = FakeRepo()
    make(repo, FakeEmbedder()).search(
        "q", scope="body", theme="ECON*", domain="e.com", min_negativity=8.0
    )
    assert repo.filters
    assert all(
        (f.theme, f.domain, f.min_negativity) == ("ECON*", "e.com", 8.0)
        for f in repo.filters
    )


@pytest.mark.parametrize("scope", ["body", "all"])
def test_vector_mode_without_embedding_raises(scope: str) -> None:
    emb = FakeEmbedder()
    emb.down = True
    with pytest.raises(EmbeddingUnavailable):
        make(FakeRepo(), emb).search("q", mode="vector", scope=scope)


def test_hybrid_without_embedding_keeps_the_keyword_legs_and_is_degraded() -> None:
    repo, emb = FakeRepo(), FakeEmbedder()
    emb.down = True
    repo.legs["body_keyword"] = [hit("a", None, "words")]
    body = make(repo, emb).search("q", scope="body")
    assert body.degraded is True
    assert repo.calls == ["body_keyword"]
    assert body.articles[0].matched_by == ["body_keyword"]

    repo.calls.clear()
    everything = make(repo, emb).search("q", scope="all")
    assert everything.degraded is True
    assert sorted(repo.calls) == ["body_keyword", "keyword"]
