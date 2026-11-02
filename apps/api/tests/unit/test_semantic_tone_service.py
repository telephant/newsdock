"""TC-13 (service side): the filter reaches both legs, `include` the summaries."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from newsdock_api.domain.records import ArticleSummary
from newsdock_api.domain.semantic import Hit, SearchFilters, SemanticService

T0 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
TONE_NEG = {"a": 9.5, "b": 12.5}


class ToneRepo:
    def __init__(self) -> None:
        self.filters_seen: list[SearchFilters] = []
        self.include_seen: list[tuple[str, ...]] = []

    def vector_leg(
        self, *, vector: list[float], model: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        self.filters_seen.append(filters)
        return [Hit("a", T0, 0.9), Hit("b", T0 - timedelta(minutes=1), 0.8)]

    def keyword_leg(
        self, *, query: str, filters: SearchFilters, limit: int
    ) -> list[Hit]:
        self.filters_seen.append(filters)
        return [Hit("b", T0 - timedelta(minutes=1))]

    def summaries(
        self, ids: list[str], include: Sequence[str] = ()
    ) -> dict[str, ArticleSummary]:
        self.include_seen.append(tuple(include))
        out = {}
        for i in ids:
            tone = {"tone_neg": TONE_NEG[i]} if "tone_neg" in include else {}
            out[i] = ArticleSummary(
                article_id=i, title=i, url=f"https://e.com/{i}", domain="e.com",
                published_at=T0, themes=[], seq=1, **tone,
            )  # fmt: skip
        return out


class Embedder:
    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def _service(repo: ToneRepo) -> SemanticService:
    return SemanticService(
        repo, Embedder(), model="m1", candidates=50, rrf_k=60,
        max_query_length=500, default_limit=20, max_limit=100,
    )  # fmt: skip


def test_min_negativity_is_in_the_filters_of_both_legs() -> None:
    repo = ToneRepo()
    _service(repo).search("rates", mode="hybrid", min_negativity=8.5)
    assert len(repo.filters_seen) == 2  # vector leg and keyword leg
    assert {f.min_negativity for f in repo.filters_seen} == {8.5}


def test_no_filter_means_none_and_the_other_filters_still_travel() -> None:
    repo = ToneRepo()
    _service(repo).search("rates", mode="vector", domain="e.com", theme="ECON_*")
    (seen,) = repo.filters_seen
    assert seen.min_negativity is None
    assert (seen.domain, seen.theme) == ("e.com", "ECON_*")


def test_include_goes_to_the_summaries_and_hits_carry_the_numbers() -> None:
    repo = ToneRepo()
    result = _service(repo).search("rates", mode="hybrid", include=("tone_neg",))
    assert repo.include_seen == [("tone_neg",)]
    by_id = {h.article_id: h for h in result.articles}
    assert by_id["a"].tone_neg == 9.5 and by_id["b"].tone_neg == 12.5
    assert set(by_id["a"].to_json(("tone_neg",))) >= {"score", "matched_by", "tone_neg"}


def test_without_include_the_summaries_are_asked_for_nothing_extra() -> None:
    repo = ToneRepo()
    result = _service(repo).search("rates", mode="vector")
    assert repo.include_seen == [()]
    assert all(h.tone_neg is None for h in result.articles)
