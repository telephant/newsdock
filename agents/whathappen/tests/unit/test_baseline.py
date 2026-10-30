"""Baseline model: rolling window, bounded entries, warm/cold (TC-20, AC-5, AC-14)."""

from datetime import UTC, datetime, timedelta

from whathappen.domain.baseline import Baseline, BaselineEntry, entry_from_counts

T0 = datetime(2026, 10, 30, 0, 7, tzinfo=UTC)


def entry(i: int, articles: int = 1000, **themes: int) -> BaselineEntry:
    return BaselineEntry(at=T0 + timedelta(hours=i), articles=articles, themes=themes)


def test_empty_baseline_is_cold_and_has_no_latest() -> None:
    b = Baseline()
    assert b.entries == []
    assert not b.is_warm(3)
    assert b.latest_at is None


def test_is_warm_needs_the_minimum_number_of_entries() -> None:
    b = Baseline(entries=[entry(0), entry(1)])
    assert not b.is_warm(3)
    assert Baseline(entries=[entry(0), entry(1), entry(2)]).is_warm(3)


def test_append_keeps_only_the_newest_entries_and_drops_the_oldest() -> None:
    b = Baseline()
    for i in range(26):
        b = b.append(entry(i), keep=24)
    assert len(b.entries) == 24
    assert b.entries[0].at == T0 + timedelta(hours=2)  # 0 and 1 were dropped
    assert b.latest_at == T0 + timedelta(hours=25)


def test_append_does_not_change_the_original() -> None:
    b = Baseline(entries=[entry(0)])
    b.append(entry(1), keep=24)
    assert len(b.entries) == 1


def test_pooled_share_is_total_theme_count_over_total_articles() -> None:
    b = Baseline(
        entries=[
            entry(0, articles=1000, A=10),
            entry(1, articles=3000, A=90, B=30),
        ]
    )
    assert b.share("A") == 100 / 4000
    assert b.share("B") == 30 / 4000
    assert b.share("never-seen") == 0.0
    assert Baseline().share("A") == 0.0


def test_entry_from_counts_drops_skipped_and_rare_themes_and_caps_the_size() -> None:
    counts = {
        "ECON_INFLATION": 40,
        "WB_1_X": 500,  # skip-listed prefix
        "LEADER": 400,  # skip-listed (exact prefix)
        "ARMEDCONFLICT": 30,
        "RARE": 1,  # count under 2
        "ELECTION": 20,
    }
    e = entry_from_counts(
        T0, 1840, counts, skip_prefixes=("WB_", "LEADER"), themes_kept=2
    )
    assert e.at == T0
    assert e.articles == 1840
    assert e.themes == {"ECON_INFLATION": 40, "ARMEDCONFLICT": 30}


def test_json_round_trip_keeps_version_and_entries() -> None:
    b = Baseline(entries=[entry(0, A=3)])
    again = Baseline.model_validate_json(b.model_dump_json())
    assert again == b
    assert again.version == 1
