"""TC-20, TC-22, TC-23 (body-extraction AC-12, AC-13, AC-14): `semantic_search` scopes
over real passages and a real Postgres (Docker, side database)."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_api.domain.records import SemanticResult, dump_page
from newsdock_api.domain.semantic import (
    EmbeddingUnavailable,
    InvalidScope,
    SemanticService,
)
from newsdock_db.engine import make_engine
from newsdock_db.models import ArticlePassage
from newsdock_db.testing import NOW, article, make_vec
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
GOLDEN = {
    "article_id", "title", "url", "domain", "published_at", "themes",
    "scores", "source_count", "score", "matched_by",
}  # fmt: skip


class FakeEmbedder:
    def __init__(self) -> None:
        self.down = False

    def embed_query(self, query: str) -> list[float]:
        if self.down:
            raise EmbeddingUnavailable("ollama down")
        return make_vec(1.0, 0.0)


def passage(url_hash: str, idx: int, text_: str, vec: list[float]) -> ArticlePassage:
    return ArticlePassage(
        url_hash=url_hash, idx=idx, text=text_, embedding=vec, embedding_model="m1"
    )


@pytest.fixture(scope="module")
def engine(side_db: tuple[str, str]) -> Iterator[Engine]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    eng = make_engine(side_db[0])
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(eng) as session:
        session.add_all(
            [
                # matches by title only; no body
                article("T", "Central bank lifts borrowing costs",
                        vec=make_vec(1.0, 0.0), themes=["ECON_RATES"]),
                # matches only through a passage whose words are not in the query
                article("P", "Weekly market wrap", vec=make_vec(0.0, 1.0),
                        themes=["ECON_RATES"], tone_neg=9.0,
                        published_at=NOW - timedelta(hours=1)),
                # a passage far from the query, other domain and theme
                article("F", "Football results", vec=make_vec(0.0, 1.0),
                        domain="sport.example", themes=["SPORT"], tone_neg=1.0,
                        published_at=NOW - timedelta(hours=2)),
            ]
        )  # fmt: skip
        session.commit()
        session.add_all(
            [
                passage("P", 0, "Policymakers decided to raise the cost of credit.",
                        make_vec(1.0, 0.0)),
                passage("P", 1, "Shares fell as traders sold bonds.",
                        make_vec(0.7, 0.7)),
                passage("F", 0, "The home side won on penalties.", make_vec(0.0, 1.0)),
            ]
        )  # fmt: skip
        session.commit()
    yield eng
    eng.dispose()


@pytest.fixture()
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


def service(
    engine: Engine, embedder: FakeEmbedder, default_scope: str = "titles"
) -> SemanticService:
    repo = SqlSemanticRepo(engine)
    return SemanticService(
        repo,
        embedder,
        model="m1",
        candidates=20,
        rrf_k=60,
        max_query_length=500,
        default_limit=10,
        max_limit=50,
        default_scope=default_scope,
        passages=repo,
    )


def ids(result: SemanticResult) -> list[str]:
    return [a.article_id for a in result.articles]


# TC-20 (AC-12): found by meaning, with the passage and a score
@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_body_scope_finds_an_article_by_a_passage_without_the_words(
    engine: Engine, embedder: FakeEmbedder, mode: str
) -> None:
    result = service(engine, embedder).search(
        "interest rate hike", mode=mode, scope="body"
    )
    assert ids(result)[0] == "P"
    top = result.articles[0]
    assert top.passage == "Policymakers decided to raise the cost of credit."
    assert top.score > 0
    assert "body_vector" in top.matched_by
    assert "T" not in ids(result)  # no stored text, so not in the body scope


def test_body_scope_keyword_leg_matches_words_in_a_passage(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    embedder.down = True  # only the words leg can answer
    result = service(engine, embedder).search("traders bonds", scope="body")
    assert ids(result) == ["P"]
    assert result.articles[0].passage == "Shares fell as traders sold bonds."
    assert result.articles[0].matched_by == ["body_keyword"]


# TC-20 (AC-12): the usual filters apply to the passage legs
@pytest.mark.parametrize(
    ("filters", "expected_missing"),
    [
        ({"theme": "SPORT"}, "P"),
        ({"theme": "ECON*"}, "F"),
        ({"domain": "sport.example"}, "P"),
        ({"min_negativity": 5.0}, "F"),
        ({"time_from": NOW - timedelta(minutes=90)}, "F"),
        ({"time_to": NOW - timedelta(minutes=90)}, "P"),
    ],
)
def test_filters_exclude_what_they_should(
    engine: Engine,
    embedder: FakeEmbedder,
    filters: dict[str, object],
    expected_missing: str,
) -> None:
    for mode in ("vector", "hybrid"):
        result = service(engine, embedder).search(
            "interest rate hike",
            mode=mode,
            scope="body",
            **filters,  # type: ignore[arg-type]
        )
        assert expected_missing not in ids(result), (mode, filters)
        assert result.articles, (mode, filters)


def test_one_hit_per_article_with_its_nearest_passage(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    result = service(engine, embedder).search("q", mode="vector", scope="body")
    assert ids(result).count("P") == 1
    assert (
        result.articles[0].passage
        == "Policymakers decided to raise the cost of credit."
    )


# TC-22 (AC-13): all = titles + text
def test_all_scope_returns_title_only_text_only_and_bodyless_articles(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    result = service(engine, embedder).search("q", mode="vector", scope="all")
    found = {a.article_id: a for a in result.articles}
    assert {"T", "P"} <= set(found)
    assert "vector" in found["T"].matched_by and found["T"].passage is None
    assert "body_vector" in found["P"].matched_by
    assert found["P"].passage == "Policymakers decided to raise the cost of credit."


def test_the_payload_has_a_passage_key_only_for_body_and_all(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    svc = service(engine, embedder)
    titles = dump_page(svc.search("q"))
    assert all(set(a) == GOLDEN for a in titles["articles"])
    assert set(titles) == {"articles", "mode", "degraded"}
    for scope in ("body", "all"):
        page = dump_page(svc.search("q", scope=scope))
        assert all(set(a) == GOLDEN | {"passage"} for a in page["articles"])
        assert set(page) == {"articles", "mode", "degraded"}


def test_titles_scope_equals_the_default_and_ignores_passages(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    svc = service(engine, embedder)
    default = dump_page(svc.search("q"))
    assert default == dump_page(svc.search("q", scope="titles"))


def test_the_default_scope_setting_changes_the_default(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    page = dump_page(service(engine, embedder, default_scope="all").search("q"))
    assert all("passage" in a for a in page["articles"])


def test_unknown_scope_is_invalid(engine: Engine, embedder: FakeEmbedder) -> None:
    with pytest.raises(InvalidScope):
        service(engine, embedder).search("q", scope="text")


# TC-23 (AC-14): the embedding service is down
@pytest.mark.parametrize("scope", ["body", "all"])
def test_without_embedding_vector_fails_and_hybrid_degrades(
    engine: Engine, embedder: FakeEmbedder, scope: str
) -> None:
    embedder.down = True
    svc = service(engine, embedder)
    with pytest.raises(EmbeddingUnavailable):
        svc.search("traders bonds", mode="vector", scope=scope)
    result = svc.search("traders bonds", mode="hybrid", scope=scope)
    assert result.degraded is True
    assert "P" in ids(result)
    assert all("vector" not in "".join(a.matched_by) for a in result.articles)
