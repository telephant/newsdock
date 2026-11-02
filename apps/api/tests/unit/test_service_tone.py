"""TC-12/TC-19 (service side): `min_negativity` and `include` reach the repo."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from newsdock_api.domain.service import ArticleService, ServiceLimits

LIMITS = ServiceLimits(
    search_default=20,
    search_max=100,
    list_new_default=50,
    list_new_max=200,
    max_payload_bytes=64 * 1024,
    first_run_window=timedelta(hours=1),
)
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


class Recorder:
    def __init__(self) -> None:
        self.search_kw: dict[str, Any] = {}
        self.list_kw: dict[str, Any] = {}

    def search(self, **kwargs: Any) -> list[Any]:
        self.search_kw = kwargs
        return []

    def list_new(self, **kwargs: Any) -> list[Any]:
        self.list_kw = kwargs
        return []

    def latest_seq(self) -> int | None:
        return None

    def upsert_analysis(self, *args: Any) -> bool:
        return True


def _service(repo: Recorder) -> ArticleService:
    return ArticleService(repo, limits=LIMITS, now=lambda: NOW)


def test_search_passes_the_filter_and_include_through() -> None:
    repo = Recorder()
    _service(repo).search(min_negativity=8.5, include=("tone_neg",), theme="ECON_*")
    assert repo.search_kw["min_negativity"] == 8.5
    assert repo.search_kw["include"] == ("tone_neg",)
    assert repo.search_kw["theme"] == "ECON_*"


def test_search_defaults_mean_no_filter_and_no_extra_fields() -> None:
    repo = Recorder()
    _service(repo).search()
    assert repo.search_kw["min_negativity"] is None
    assert repo.search_kw["include"] == ()


def test_list_new_passes_the_filter_and_include_through() -> None:
    repo = Recorder()
    _service(repo).list_new(
        cursor=None, limit=None, min_negativity=12.0, include=("tone", "tone_pos")
    )
    assert repo.list_kw["min_negativity"] == 12.0
    assert repo.list_kw["include"] == ("tone", "tone_pos")


def test_list_new_defaults_and_cursor_are_unchanged() -> None:
    repo = Recorder()
    page = _service(repo).list_new(cursor=None, limit=None)
    assert repo.list_kw["min_negativity"] is None
    assert repo.list_kw["include"] == ()
    assert page.articles == [] and page.next_cursor  # an empty page keeps a cursor


def test_include_is_a_sequence_not_consumed() -> None:
    include: Sequence[str] = ("tone",)
    repo = Recorder()
    _service(repo).search(include=include)
    assert tuple(repo.search_kw["include"]) == ("tone",)
