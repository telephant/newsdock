"""TC-13 (AC-10) and the service half of AC-4: `min_negativity` in both search legs,
and hits carrying the requested tone numbers (Docker, hand-made vectors)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_api.domain.semantic import SearchFilters, SemanticService
from newsdock_db.engine import make_engine
from newsdock_db.testing import article, make_vec
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
QUERY = make_vec(1.0, 0.0)


class FakeEmbedder:
    def embed_query(self, query: str) -> list[float]:
        return QUERY


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(eng) as session:
        session.add_all(
            [
                article("A", "Central bank raises interest rates",
                        vec=make_vec(1.0, 0.0), tone=-4.0, tone_neg=9.5),
                article("B", "Wildfire spreads across the hills",
                        vec=make_vec(0.8, 0.6), tone=2.0, tone_neg=3.0),
                article("C", "Interest rates tumble sharply",
                        vec=make_vec(0.6, 0.8), tone=-12.0, tone_neg=12.5),
                article("D", "Opposition wins the vote",
                        vec=make_vec(0.0, 1.0), tone=-8.0, tone_neg=8.0),
                article("E", "Interest rates explained for beginners",
                        vec=make_vec(1.0, 0.0)),  # embedded but no tone
                article("F", "Rates outlook darkens",
                        vec=make_vec(0.9, 0.1), tone=-9.7, tone_neg=9.7),
            ]
        )  # fmt: skip
        session.commit()
    yield eng
    eng.dispose()


def _service(engine: Engine) -> SemanticService:
    return SemanticService(
        SqlSemanticRepo(engine), FakeEmbedder(), model="m1", candidates=50,
        rrf_k=60, max_query_length=500, default_limit=20, max_limit=100,
    )  # fmt: skip


def _ids(hits: list) -> set[str]:  # type: ignore[type-arg]
    return {h.id for h in hits}


def test_vector_leg_applies_the_filter(engine: Engine) -> None:
    repo = SqlSemanticRepo(engine)
    wide = repo.vector_leg(vector=QUERY, model="m1", filters=SearchFilters(), limit=20)
    assert _ids(wide) == {"A", "B", "C", "D", "E", "F"}
    narrow = repo.vector_leg(
        vector=QUERY, model="m1", filters=SearchFilters(min_negativity=8), limit=20
    )
    assert _ids(narrow) == {"A", "C", "D", "F"}
    exact = repo.vector_leg(
        vector=QUERY, model="m1", filters=SearchFilters(min_negativity=9.7), limit=20
    )
    assert _ids(exact) == {"C", "F"}


def test_keyword_leg_applies_the_same_filter(engine: Engine) -> None:
    repo = SqlSemanticRepo(engine)
    wide = repo.keyword_leg(query="interest rates", filters=SearchFilters(), limit=20)
    assert _ids(wide) == {"A", "C", "E"}
    narrow = repo.keyword_leg(
        query="interest rates", filters=SearchFilters(min_negativity=8), limit=20
    )
    assert _ids(narrow) == {"A", "C"}  # E has no tone_neg


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_service_results_match_search_articles_on_the_embedded_rows(
    engine: Engine, mode: str
) -> None:
    result = _service(engine).search(
        "interest rates", mode=mode, min_negativity=8, include=("tone_neg",)
    )
    got = {h.article_id for h in result.articles}
    expected = {
        a.article_id
        for a in SqlArticleRepo(engine).search(
            time_from=None,
            time_to=None,
            theme=None,
            domain=None,
            text=None,
            limit=50,
            min_negativity=8,
        )  # fmt: skip
    }
    assert got <= expected  # hybrid's keyword leg may match fewer rows, never more
    if mode == "vector":
        assert got == expected
    assert all(h.tone_neg is not None and h.tone_neg >= 8 for h in result.articles)


def test_hits_carry_requested_numbers_and_keep_score_and_matched_by(
    engine: Engine,
) -> None:
    result = _service(engine).search("interest rates", mode="vector", include=("tone",))
    by_id = {h.article_id: h for h in result.articles}
    assert by_id["A"].tone == -4.0 and by_id["C"].tone == -12.0
    assert by_id["E"].tone is None  # a row without tone
    assert by_id["A"].tone_neg is None  # not requested, not filled
    out = by_id["A"].to_json(("tone",))
    assert out["matched_by"] == ["vector"] and "score" in out and out["tone"] == -4.0


def test_default_search_is_unchanged(engine: Engine) -> None:
    result = _service(engine).search("interest rates", mode="vector")
    assert {h.article_id for h in result.articles} == {"A", "B", "C", "D", "E", "F"}
    assert all(h.tone is None and h.tone_neg is None for h in result.articles)
