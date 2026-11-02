"""TC-12 (AC-9), TC-19 (AC-14), and the repo half of AC-2, AC-3, AC-8 (Docker).

Rows A-F of tests.md section 1 on a side Postgres: `min_negativity` through the one
filter implementation, `include` filling only the requested tone numbers, and the
detail carrying all four.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_db.engine import make_engine
from newsdock_db.testing import NOW, article
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
OLD = NOW - timedelta(days=3)


@pytest.fixture(scope="module")
def repo(side_db: tuple[str, str]) -> Iterator[SqlArticleRepo]:
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    engine = make_engine(side_db[0])
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(engine) as session:
        session.add_all(
            [
                article("A", "Central bank raises rates", domain="a.com",
                        themes=["ECON_RATES"], tone=-4.0, tone_pos=1.5,
                        tone_neg=9.5, tone_polarity=11.0),
                article("B", "Wildfire spreads across the hills", domain="a.com",
                        themes=["ENV_FIRE"], tone=2.0, tone_pos=5.0,
                        tone_neg=3.0, tone_polarity=8.0),
                article("C", "Bond rates tumble", domain="b.com",
                        themes=["ECON_RATES"], tone=-12.0, tone_pos=0.5,
                        tone_neg=12.5, tone_polarity=13.0, published_at=OLD),
                article("D", "Election result disputed", domain="a.com",
                        themes=["GOV_VOTE"], tone=-8.0, tone_pos=0.0,
                        tone_neg=8.0, tone_polarity=8.0, published_at=OLD),
                article("E", "No tone for this one", domain="c.com"),
                article("F", "Rates outlook darkens", domain="b.com",
                        themes=["ECON_RATES"], tone=-9.7, tone_pos=0.0,
                        tone_neg=9.7, tone_polarity=9.7),
            ]
        )  # fmt: skip
        session.commit()
    yield SqlArticleRepo(engine)
    engine.dispose()


def _search(repo: SqlArticleRepo, **kw: Any) -> list[Any]:
    args: dict[str, Any] = {
        "time_from": None, "time_to": None, "theme": None, "domain": None,
        "text": None, "limit": 50,
    }  # fmt: skip
    args.update(kw)
    return repo.search(**args)


def _ids(rows: list[Any]) -> set[str]:
    return {r.article_id for r in rows}


def _new(repo: SqlArticleRepo, **kw: Any) -> list[Any]:
    return repo.list_new(after_seq=0, since=None, limit=50, **kw)


def test_without_the_filter_every_row_comes_back_even_without_tone(
    repo: SqlArticleRepo,
) -> None:
    assert _ids(_search(repo)) == {"A", "B", "C", "D", "E", "F"}


def test_min_negativity_is_inclusive_and_skips_rows_without_tone(
    repo: SqlArticleRepo,
) -> None:
    assert _ids(_search(repo, min_negativity=8)) == {"A", "C", "D", "F"}
    assert _ids(_search(repo, min_negativity=8.0001)) == {"A", "C", "F"}


def test_a_value_typed_with_a_decimal_matches_the_stored_real(
    repo: SqlArticleRepo,
) -> None:
    # F is stored as the float4 9.7; a float8 9.7 would be larger and drop it.
    assert _ids(_search(repo, min_negativity=9.7)) == {"C", "F"}
    assert _ids(_search(repo, min_negativity=9.5)) == {"A", "C", "F"}


def test_zero_and_one_hundred_are_the_edges(repo: SqlArticleRepo) -> None:
    assert _ids(_search(repo, min_negativity=0)) == {"A", "B", "C", "D", "F"}
    assert _search(repo, min_negativity=100) == []


def test_list_new_filters_the_same_way(repo: SqlArticleRepo) -> None:
    assert _ids(_new(repo, min_negativity=8)) == {"A", "C", "D", "F"}
    assert _ids(_new(repo, min_negativity=9.7)) == {"C", "F"}
    assert _ids(_new(repo)) == {"A", "B", "C", "D", "E", "F"}


def test_filters_combine_with_and(repo: SqlArticleRepo) -> None:
    assert _ids(_search(repo, min_negativity=8, theme="ECON_*")) == {"A", "C", "F"}
    assert _ids(_search(repo, min_negativity=8, theme="ECON_*", domain="b.com")) == {
        "C",
        "F",
    }
    assert _ids(_search(repo, min_negativity=8, text="rates")) == {"A", "C", "F"}
    assert _ids(_search(repo, min_negativity=8, time_from=NOW - timedelta(days=1))) == {
        "A",
        "F",
    }
    assert _ids(_search(repo, min_negativity=8, time_to=NOW - timedelta(days=1))) == {
        "C",
        "D",
    }
    assert _ids(
        _new(repo, min_negativity=8, theme="ECON_*", domain="b.com", text="bond")
    ) == {"C"}


def test_include_fills_only_the_requested_numbers(repo: SqlArticleRepo) -> None:
    rows = {r.article_id: r for r in _search(repo, include=("tone_neg",))}
    assert rows["A"].tone_neg == 9.5
    assert rows["A"].tone is None and rows["A"].tone_pos is None
    assert rows["A"].tone_polarity is None
    assert rows["B"].tone_neg == 3.0
    assert rows["E"].tone_neg is None
    assert rows["A"].to_json(("tone_neg",))["tone_neg"] == 9.5


def test_without_include_no_number_is_filled(repo: SqlArticleRepo) -> None:
    for row in _search(repo) + _new(repo):
        assert (row.tone, row.tone_pos, row.tone_neg, row.tone_polarity) == (
            None,
            None,
            None,
            None,
        )


def test_list_new_include_and_summaries_include(repo: SqlArticleRepo) -> None:
    fresh = {r.article_id: r for r in _new(repo, include=("tone", "tone_neg"))}
    assert (fresh["C"].tone, fresh["C"].tone_neg) == (-12.0, 12.5)
    assert fresh["C"].tone_pos is None
    got = repo.summaries(["A", "E"], include=("tone", "tone_neg"))
    assert (got["A"].tone, got["A"].tone_neg) == (-4.0, 9.5)
    assert (got["E"].tone, got["E"].tone_neg) == (None, None)
    assert repo.summaries(["A"])["A"].tone is None  # default stays empty


def test_include_keeps_the_page_the_same(repo: SqlArticleRepo) -> None:
    plain = [r.article_id for r in _new(repo)]
    with_tone = [r.article_id for r in _new(repo, include=("tone",))]
    assert plain == with_tone
    assert [r.seq for r in _new(repo)] == [r.seq for r in _new(repo, include=("tone",))]


def test_detail_carries_all_four_numbers(repo: SqlArticleRepo) -> None:
    detail = repo.get("A")
    assert detail is not None
    assert (detail.tone, detail.tone_pos, detail.tone_neg, detail.tone_polarity) == (
        -4.0,
        1.5,
        9.5,
        11.0,
    )
    empty = repo.get("E")
    assert empty is not None
    assert (empty.tone, empty.tone_neg, empty.tone_pos) == (None, None, None)
