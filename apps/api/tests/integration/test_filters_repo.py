"""TC-18 (AC-6, AC-7): filtered list_new and the shared theme prefix (Docker)."""

import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_db.engine import make_engine
from newsdock_db.models import Article
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "newsdock-filters-test"
NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", ".env.example",
         "-f", "infra/compose.yaml", *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def _article(key: str, themes: list[str], domain: str, title: str) -> Article:
    return Article(
        url_hash=key, gkg_record_id="x", slot="20261014120000",
        url=f"https://{domain}/{key}", title=title, domain=domain,
        published_at=NOW, themes=themes, persons=[], orgs=[], story_key=f"s {key}",
    )  # fmt: skip


@pytest.fixture(scope="module")
def repo() -> Iterator[SqlArticleRepo]:
    assert _compose("up", "-d", "--wait", "postgres").returncode == 0
    env = {
        k.strip(): v.strip()
        for k, _, v in (
            line.partition("=")
            for line in (ROOT / ".env.example").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    url = (
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{env.get('POSTGRES_PORT', '5433')}/{env['POSTGRES_DB']}"
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "infra" / "migrations" / "alembic.ini")), "head")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(engine) as session:
        session.add_all([
            _article(
                "a1", ["ECON_INFLATION", "TAX_X"], "alpha.com", "Fed raises rates"
            ),
            _article("a2", ["ENV_CLIMATE"], "beta.org", "Storm season 100% wet"),
            _article(
                "a3", ["WB_1", "ECON_STOCKMARKET"], "alpha.com", "Stocks rally"
            ),
            _article("a4", [], "gamma.net", "No themes"),
            _article("a5", ["ECONOMY_X"], "alpha.com", "Not an ECON_ prefix"),
        ])  # fmt: skip
        session.commit()
    yield SqlArticleRepo(engine)
    engine.dispose()
    mp.undo()
    _compose("down", "-v", "--remove-orphans")


def _ids(rows: list) -> list[str]:  # type: ignore[type-arg]
    return [r.article_id for r in rows]


def _new(repo: SqlArticleRepo, **filters: str | None) -> list[str]:
    return _ids(repo.list_new(after_seq=0, since=None, limit=50, **filters))


def test_no_filter_keeps_the_m1_behaviour_in_seq_order(repo: SqlArticleRepo) -> None:
    assert _new(repo) == ["a1", "a2", "a3", "a4", "a5"]


def test_theme_prefix_matches_any_of_the_articles_themes(repo: SqlArticleRepo) -> None:
    assert _new(repo, theme="ECON_*") == ["a1", "a3"]  # a5 is ECONOMY_, not ECON_
    assert _new(repo, theme="WB_*") == ["a3"]


def test_exact_theme_still_matches_exactly(repo: SqlArticleRepo) -> None:
    assert _new(repo, theme="ECON_INFLATION") == ["a1"]
    assert _new(repo, theme="ECON_") == []  # a bare prefix without '*' is exact


def test_domain_and_text_filters_and_and_semantics(repo: SqlArticleRepo) -> None:
    assert _new(repo, domain="alpha.com") == ["a1", "a3", "a5"]
    assert _new(repo, text="stocks") == ["a3"]  # case-insensitive title text
    assert _new(repo, theme="ECON_*", domain="alpha.com", text="rally") == ["a3"]
    assert _new(repo, theme="ECON_*", domain="beta.org") == []


def test_like_wildcards_in_user_text_are_literal(repo: SqlArticleRepo) -> None:
    assert _new(repo, text="100%") == ["a2"]
    assert _new(repo, text="%") == ["a2"]  # only titles that contain a real '%'
    assert _new(repo, theme="ECON_%*") == []  # '%' in a prefix is not a wildcard


def test_after_seq_and_filters_combine(repo: SqlArticleRepo) -> None:
    first = repo.list_new(after_seq=0, since=None, limit=50, domain="alpha.com")
    after_first = repo.list_new(
        after_seq=first[0].seq, since=None, limit=50, domain="alpha.com"
    )
    assert _ids(after_first) == ["a3", "a5"]


def test_search_articles_shares_the_prefix_syntax(repo: SqlArticleRepo) -> None:
    found = repo.search(
        time_from=None, time_to=None, theme="ECON_*", domain=None, text=None, limit=20
    )
    assert sorted(_ids(found)) == ["a1", "a3"]
