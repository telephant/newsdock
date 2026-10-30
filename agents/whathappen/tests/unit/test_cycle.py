"""DigestCycle (TC-1, 2, 4, 5, 15, 17; AC-1, AC-2, AC-3, AC-10, AC-11)."""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from whathappen.adapters.files import DigestWriter
from whathappen.domain.articles import Article
from whathappen.domain.baseline import Baseline, BaselineEntry
from whathappen.domain.digest import DigestCycle, DigestParams

NOW = datetime(2026, 10, 30, 14, 7, tzinfo=UTC)


def params(**overrides: object) -> DigestParams:
    base: dict[str, object] = {
        "page_size": 200,
        "max_articles": 20000,
        "skip_prefixes": (),
        "min_theme_count": 2,
        "max_themes": 8,
        "stories_per_theme": 3,
        "prompt_titles": 8,
        "baseline_hours": 24,
        "baseline_min_entries": 3,
        "themes_kept": 2000,
    }
    base.update(overrides)
    return DigestParams(**base)  # type: ignore[arg-type]


class Events(list[str]):
    """One shared log so the call order across the ports can be asserted."""


class FakeMcp:
    """Scripted pages; page i has cursor f'c{i + 1}'. Beyond the script: empty."""

    def __init__(self, events: Events, pages: list[list[dict[str, object]]]) -> None:
        self.events = events
        self.pages = pages
        self.list_calls: list[tuple[int, str | None]] = []
        self.acks: list[str] = []

    def list_new_articles(
        self, limit: int, cursor: str | None = None
    ) -> tuple[list[dict[str, object]], str]:
        self.list_calls.append((limit, cursor))
        self.events.append("list")
        i = len(self.list_calls) - 1
        if i < len(self.pages):
            return self.pages[i], f"c{i + 1}"
        return [], cursor or "c0"

    def ack_cursor(self, cursor: str) -> None:
        self.events.append(f"ack:{cursor}")
        self.acks.append(cursor)


class FakeSink:
    def __init__(self, events: Events, fail: bool = False) -> None:
        self.events = events
        self.fail = fail
        self.writes: list[tuple[datetime, str]] = []

    def write(self, now: datetime, text: str) -> Path:
        if self.fail:
            raise OSError("disk full")
        self.events.append("write")
        self.writes.append((now, text))
        return Path("/digests/fake.md")


class FakeStore:
    def __init__(
        self, events: Events, baseline: Baseline | None = None, fail_save: bool = False
    ) -> None:
        self.events = events
        self.baseline = baseline or Baseline()
        self.fail_save = fail_save
        self.saved: list[Baseline] = []

    def load(self) -> Baseline:
        return self.baseline

    def save(self, baseline: Baseline) -> None:
        if self.fail_save:
            raise OSError("read-only")
        self.events.append("save")
        self.saved.append(baseline)


class FakeSummariser:
    def __init__(
        self, answers: dict[str, str | None | Exception] | None = None
    ) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, list[str]]] = []

    def summarise(self, label: str, titles: Sequence[str]) -> str | None:
        self.calls.append((label, list(titles)))
        answer = self.answers.get(label, f"About {label}.")
        if isinstance(answer, Exception):
            raise answer
        return answer


def raw(article: Article) -> dict[str, object]:
    return article.model_dump(mode="json")


@pytest.fixture
def page(
    make_article: Callable[..., Article],
) -> Callable[..., list[dict[str, object]]]:
    def make(start: int, n: int, themes: list[str]) -> list[dict[str, object]]:
        return [raw(make_article(start + i, themes=themes)) for i in range(n)]

    return make


def cycle(
    mcp: FakeMcp,
    sink: FakeSink,
    store: FakeStore,
    summariser: FakeSummariser | None = None,
    **overrides: object,
) -> DigestCycle:
    return DigestCycle(
        mcp, summariser or FakeSummariser(), sink, store, params(**overrides)
    )


# ---- TC-1: the whole window ----------------------------------------------------


def test_tc1_reads_every_page_until_a_short_one(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    mcp = FakeMcp(
        events, [page(0, 200, ["T"]), page(200, 200, ["T"]), page(400, 37, ["T"])]
    )
    result = cycle(mcp, FakeSink(events), FakeStore(events)).run_once(NOW)
    assert result is not None and result.article_count == 437
    assert mcp.list_calls == [(200, None), (200, "c1"), (200, "c2")]  # no 4th page
    assert mcp.acks == ["c3"]


def test_tc1_a_full_last_page_means_one_more_empty_page_is_requested(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    mcp = FakeMcp(events, [page(0, 200, ["T"])])
    result = cycle(mcp, FakeSink(events), FakeStore(events)).run_once(NOW)
    assert result is not None and result.article_count == 200
    assert mcp.list_calls == [(200, None), (200, "c1")]
    assert mcp.acks == ["c1"]  # the empty page returns the cursor it was given


def test_tc2_paging_stops_at_the_article_cap_and_acks_what_was_read(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    pages = [page(i * 200, 200, ["T"]) for i in range(3)]
    mcp = FakeMcp(events, pages)
    result = cycle(mcp, FakeSink(events), FakeStore(events), max_articles=300).run_once(
        NOW
    )
    assert result is not None and result.article_count == 400  # whole pages
    assert len(mcp.list_calls) == 2
    assert mcp.acks == ["c2"]  # the next cycle continues from here


def test_a_malformed_article_is_skipped_not_fatal(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    bad: dict[str, object] = {"article_id": "x"}  # no title, url or date
    mcp = FakeMcp(events, [[*page(0, 3, ["T"]), bad]])
    result = cycle(mcp, FakeSink(events), FakeStore(events)).run_once(NOW)
    assert result is not None and result.article_count == 3
    assert mcp.acks == ["c1"]


# ---- TC-4 / TC-5: ack only after the file --------------------------------------


def test_tc4_order_is_read_then_write_then_ack_then_baseline(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    sink = FakeSink(events)
    mcp = FakeMcp(events, [page(0, 5, ["T"])])
    cycle(mcp, sink, FakeStore(events)).run_once(NOW)
    non_list = [e for e in events if e != "list"]
    assert non_list == ["write", "ack:c1", "save"]
    assert len(mcp.acks) == 1
    assert sink.writes[0][0] == NOW and sink.writes[0][1].startswith("# What happened")


def test_tc4_the_digest_text_is_also_logged(
    page: Callable[..., list[dict[str, object]]], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    events = Events()
    cycle(
        FakeMcp(events, [page(0, 5, ["T"])]), FakeSink(events), FakeStore(events)
    ).run_once(NOW)
    assert any("# What happened" in r.getMessage() for r in caplog.records)


def test_tc5_an_unwritable_directory_means_no_ack_and_the_window_is_read_again(
    page: Callable[..., list[dict[str, object]]], tmp_path: Path
) -> None:
    events = Events()
    store = FakeStore(events)
    readonly = tmp_path / "ro"
    readonly.mkdir()
    readonly.chmod(0o500)
    first = FakeMcp(events, [page(0, 5, ["T"])])
    try:
        with pytest.raises(OSError):
            DigestCycle(
                first,
                FakeSummariser(),
                DigestWriter(readonly / "digests"),
                store,
                params(),
            ).run_once(NOW)
    finally:
        readonly.chmod(0o700)
    assert first.acks == [] and store.saved == []  # nothing acked, baseline untouched
    # the next cycle gets the same window again from the server and succeeds
    second = FakeMcp(events, [page(0, 5, ["T"])])
    result = DigestCycle(
        second, FakeSummariser(), DigestWriter(tmp_path / "ok"), store, params()
    ).run_once(NOW)
    assert result is not None and result.path.is_file()
    assert second.acks == ["c1"] and len(store.saved) == 1


def test_a_failing_ack_surfaces_after_the_file_was_written(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()

    class BadAck(FakeMcp):
        def ack_cursor(self, cursor: str) -> None:
            raise RuntimeError("api down")

    sink, store = FakeSink(events), FakeStore(events)
    with pytest.raises(RuntimeError):
        cycle(BadAck(events, [page(0, 3, ["T"])]), sink, store).run_once(NOW)
    assert len(sink.writes) == 1 and store.saved == []  # a duplicate digest later is ok


# ---- TC-15: a failing summary only affects its own section --------------------------


def test_tc15_one_failing_theme_degrades_one_section(
    make_article: Callable[..., Article],
) -> None:
    events = Events()
    articles = [raw(make_article(i, themes=["A_X"])) for i in range(3)]
    articles += [raw(make_article(10 + i, themes=["B_Y"])) for i in range(3)]
    articles += [raw(make_article(20 + i, themes=["C_Z"])) for i in range(3)]
    sink = FakeSink(events)
    mcp = FakeMcp(events, [articles])
    summariser = FakeSummariser({"B Y": RuntimeError("model blew up"), "C Z": None})
    result = cycle(mcp, sink, FakeStore(events), summariser).run_once(NOW)
    assert result is not None
    text = sink.writes[0][1]
    assert "About A X." in text
    assert text.count("Summary unavailable.") == 2  # the raiser and the None
    assert text.count("\n## ") == 3  # every section is still there, with links
    assert text.count("- [") == 9
    assert mcp.acks == ["c1"]  # file written, cursor acked


# ---- TC-17: a quiet hour --------------------------------------------------------


def test_tc17_an_empty_window_writes_nothing_and_acks_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    events = Events()
    sink, store = FakeSink(events), FakeStore(events)
    mcp = FakeMcp(events, [[]])
    assert cycle(mcp, sink, store).run_once(NOW) is None
    assert sink.writes == [] and mcp.acks == [] and store.saved == []
    assert any("empty window" in r.getMessage() for r in caplog.records)


def test_a_window_of_only_malformed_rows_is_acked_but_writes_nothing() -> None:
    events = Events()
    sink, store = FakeSink(events), FakeStore(events)
    mcp = FakeMcp(events, [[{"article_id": "x"}]])
    assert cycle(mcp, sink, store).run_once(NOW) is None
    assert sink.writes == [] and mcp.acks == ["c1"]


# ---- baseline, since and prompts -----------------------------------------------


def test_the_baseline_gets_this_cycles_counts_and_skip_listed_themes_stay_out(
    make_article: Callable[..., Article],
) -> None:
    events = Events()
    articles = [raw(make_article(i, themes=["ECON_X", "WB_1"])) for i in range(4)]
    store = FakeStore(events)
    cycle(
        FakeMcp(events, [articles]), FakeSink(events), store, skip_prefixes=("WB_",)
    ).run_once(NOW)
    [saved] = store.saved
    assert len(saved.entries) == 1
    assert saved.entries[0].at == NOW and saved.entries[0].articles == 4
    assert saved.entries[0].themes == {"ECON_X": 4}


def test_a_failing_baseline_save_does_not_fail_the_cycle(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    mcp = FakeMcp(events, [page(0, 3, ["T"])])
    result = cycle(mcp, FakeSink(events), FakeStore(events, fail_save=True)).run_once(
        NOW
    )
    assert result is not None and mcp.acks == ["c1"]


def test_since_comes_from_the_previous_baseline_entry_and_cold_start_is_marked(
    page: Callable[..., list[dict[str, object]]],
) -> None:
    events = Events()
    previous = Baseline(
        entries=[
            BaselineEntry(at=NOW - timedelta(hours=1), articles=100, themes={"T": 50})
        ]
    )
    sink = FakeSink(events)
    cycle(
        FakeMcp(events, [page(0, 6, ["T"])]), sink, FakeStore(events, previous)
    ).run_once(NOW)
    text = sink.writes[0][1]
    assert "(6 articles · since 13:07)" in text
    assert "no baseline yet" in text  # one entry is still cold


def test_the_model_gets_the_theme_label_and_its_own_titles_only(
    make_article: Callable[..., Article],
) -> None:
    events = Events()
    articles = [
        raw(make_article(i, themes=["ECON_X"], title=f"Econ {i}")) for i in range(3)
    ]
    summariser = FakeSummariser()
    cycle(
        FakeMcp(events, [articles]), FakeSink(events), FakeStore(events), summariser
    ).run_once(NOW)
    assert summariser.calls == [("ECON X", ["Econ 0", "Econ 1", "Econ 2"])]
