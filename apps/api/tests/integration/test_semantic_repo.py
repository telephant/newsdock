"""TC-6, TC-10, TC-12 (query half): the vector and keyword legs (Docker)."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_api.domain.semantic import Hit, SearchFilters
from newsdock_db.engine import make_engine
from newsdock_db.testing import NOW, article, make_vec
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
NO_FILTERS = SearchFilters()
QUERY = make_vec(1.0, 0.0)


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))


@pytest.fixture()
def repo(engine: Engine) -> SqlSemanticRepo:
    return SqlSemanticRepo(engine)


def add(engine: Engine, *rows: object) -> None:
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


def leg(
    repo: SqlSemanticRepo,
    filters: SearchFilters = NO_FILTERS,
    *,
    vector: list[float] = QUERY,
    model: str = "m1",
    limit: int = 10,
) -> list[Hit]:
    return repo.vector_leg(vector=vector, model=model, filters=filters, limit=limit)


# TC-6 (AC-6): nearest first, similarity = 1 - cosine distance
def test_vector_leg_orders_by_distance_with_similarity(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    add(
        engine,
        article("far", "Far", vec=make_vec(0.0, 1.0)),  # orthogonal: 0.0
        article("near", "Near", vec=make_vec(1.0, 0.0)),  # identical: 1.0
        article("mid", "Mid", vec=make_vec(1.0, 1.0)),  # 45 degrees: 0.7071
        article("opposite", "Opposite", vec=make_vec(-1.0, 0.0)),  # -1.0
    )
    hits = leg(repo)
    assert [h.id for h in hits] == ["near", "mid", "far", "opposite"]
    sims = [h.similarity for h in hits]
    assert sims == pytest.approx([1.0, 0.70710678, 0.0, -1.0], abs=1e-4)
    assert all(-1.0001 <= s <= 1.0001 for s in sims if s is not None)


def test_vector_leg_respects_the_limit_and_skips_unembedded_rows(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    add(
        engine,
        article("a", "A", vec=make_vec(1.0, 0.0)),
        article("b", "B", vec=make_vec(1.0, 0.1)),
        article("c", "C", vec=make_vec(1.0, 0.2)),
        article("none", "Not embedded yet"),
    )
    assert [h.id for h in leg(repo, limit=2)] == ["a", "b"]
    assert "none" not in [h.id for h in leg(repo)]


# TC-12 (AC-11), query half: rows from another model are never compared
def test_vector_leg_ignores_rows_embedded_with_another_model(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    add(
        engine,
        article("old", "Old model", vec=make_vec(1.0, 0.0), model="old-model"),
        article("new", "New model", vec=make_vec(1.0, 0.5), model="new-model"),
    )
    assert [h.id for h in leg(repo, model="new-model")] == ["new"]
    assert [h.id for h in leg(repo, model="old-model")] == ["old"]


# TC-10 (AC-9): the shared filters apply to the vector leg
def test_vector_leg_applies_every_filter(engine: Engine, repo: SqlSemanticRepo) -> None:
    add(
        engine,
        article("a", "A", vec=make_vec(1.0, 0.0), domain="a.com",
                themes=["ECON_INFLATION"], published_at=NOW),
        article("b", "B", vec=make_vec(1.0, 0.1), domain="b.com",
                themes=["ECON_TRADE"], published_at=NOW),
        article("c", "C", vec=make_vec(1.0, 0.2), domain="a.com",
                themes=["WB_HEALTH"], published_at=NOW - timedelta(days=3)),
    )  # fmt: skip

    def ids(filters: SearchFilters) -> list[str]:
        return [h.id for h in leg(repo, filters)]

    assert ids(SearchFilters(domain="a.com")) == ["a", "c"]
    assert ids(SearchFilters(theme="ECON_TRADE")) == ["b"]
    assert ids(SearchFilters(theme="ECON_*")) == ["a", "b"]
    assert ids(SearchFilters(time_from=NOW - timedelta(days=1))) == ["a", "b"]
    assert ids(SearchFilters(time_to=NOW - timedelta(days=1))) == ["c"]
    both = SearchFilters(
        domain="a.com", theme="ECON_*", time_from=NOW - timedelta(days=1)
    )
    assert ids(both) == ["a"]


def test_a_selective_filter_still_returns_every_match(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    rows = [
        article(f"c{i}", f"Common {i}", vec=make_vec(1.0, i / 400), domain="common.com")
        for i in range(300)
    ]
    rows += [
        article(f"r{i}", f"Rare {i}", vec=make_vec(0.0, 1.0, i / 10), domain="rare.com")
        for i in range(3)
    ]
    add(engine, *rows)
    hits = leg(repo, SearchFilters(domain="rare.com"), limit=20)
    assert sorted(h.id for h in hits) == ["r0", "r1", "r2"]


# keyword leg (D-8): full-text on the title, stemmed, ranked, same filters
def test_keyword_leg_matches_stemmed_words_and_ranks_by_relevance(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    add(
        engine,
        article("one", "Central bank raises interest rates again"),
        article("two", "Bank holiday weekend travel"),
        article("three", "Wildfire spreads across the hills"),
    )
    hits = repo.keyword_leg(query="bank raising rates", filters=NO_FILTERS, limit=10)
    assert [h.id for h in hits][0] == "one"  # "raising" matches "raises", two words hit
    assert "three" not in [h.id for h in hits]


def test_keyword_leg_applies_the_filters_and_the_limit(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    add(
        engine,
        article("a", "Oil prices fall", domain="a.com", themes=["ECON_OIL"]),
        article("b", "Oil prices rise", domain="b.com", themes=["ECON_OIL"]),
        article("c", "Oil prices steady", domain="b.com", themes=["WB_ENERGY"]),
    )

    def ids(filters: SearchFilters) -> list[str]:
        hits = repo.keyword_leg(query="oil prices", filters=filters, limit=10)
        return [h.id for h in hits]

    assert sorted(ids(SearchFilters(domain="b.com"))) == ["b", "c"]
    assert sorted(ids(SearchFilters(theme="ECON_*"))) == ["a", "b"]
    assert len(repo.keyword_leg(query="oil", filters=NO_FILTERS, limit=2)) == 2


def test_keyword_leg_survives_odd_input(engine: Engine, repo: SqlSemanticRepo) -> None:
    add(engine, article("a", "Oil prices fall"))
    for query in ["'", "a & | !", "(((", "oil OR", '"unterminated', "%_\\"]:
        repo.keyword_leg(query=query, filters=NO_FILTERS, limit=5)  # must not raise


def test_keyword_leg_uses_the_full_text_index(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SET enable_seqscan = off"))
        plan = conn.execute(
            text(
                "EXPLAIN SELECT url_hash FROM articles WHERE "
                "to_tsvector('english', title) @@ "
                "websearch_to_tsquery('english', 'oil')"
            )
        ).all()
    assert "ix_articles_title_fts" in "\n".join(r[0] for r in plan)


# summaries: loaded after fusion, with source counts
def test_summaries_return_the_requested_articles(
    engine: Engine, repo: SqlSemanticRepo
) -> None:
    add(engine, article("a", "A"), article("b", "B"), article("c", "C"))
    found = repo.summaries(["c", "a", "missing"])
    assert set(found) == {"a", "c"}
    assert found["a"].title == "A" and found["a"].source_count == 1
    assert repo.summaries([]) == {}
