"""TC-1, TC-2, TC-5 (events part): Events row parsing against real fixture data."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from newsdock_core.contracts import CleanEvent, DlqMessage, DlqReason
from newsdock_core.events import parse_event_row
from newsdock_core.urls import url_hash

FIXTURES = Path(__file__).parent.parent / "fixtures"
SLOT = "20261102110000"


def _lines() -> list[str]:
    return (FIXTURES / "events_sample.tsv").read_text().splitlines()


def _load(name: str) -> list[dict[str, Any]]:
    with (FIXTURES / name).open() as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


def _parse(line: str, row_no: int = 0) -> CleanEvent | DlqMessage:
    return parse_event_row(slot=SLOT, row_no=row_no, line=line)


def _with(line: str, index: int, value: str) -> str:
    columns = line.split("\t")
    columns[index] = value
    return "\t".join(columns)


# TC-1: hand-checked rows equal the expected values
def test_hand_checked_rows_parse_to_expected_values() -> None:
    lines = _lines()
    for exp in _load("expected_events.json"):
        got = _parse(lines[exp["row_no"]], exp["row_no"])
        assert isinstance(got, CleanEvent), got
        assert got.event_id == exp["event_id"]
        assert got.event_date == date.fromisoformat(exp["event_date"])
        assert got.actor1.model_dump() == exp["actor1"]
        assert got.actor2.model_dump() == exp["actor2"]
        assert got.is_root is exp["is_root"]
        assert (got.cameo_code, got.cameo_base, got.cameo_root) == (
            exp["cameo_code"],
            exp["cameo_base"],
            exp["cameo_root"],
        )
        assert got.quad_class == exp["quad_class"]
        assert got.goldstein == exp["goldstein"]
        assert (got.num_mentions, got.num_sources, got.num_articles) == (
            exp["num_mentions"],
            exp["num_sources"],
            exp["num_articles"],
        )
        assert got.avg_tone == pytest.approx(exp["avg_tone"])
        assert got.geo is not None
        assert got.geo.model_dump() == exp["geo"]
        assert got.date_added == datetime(2026, 11, 2, 11, 0, tzinfo=UTC)
        assert got.source_url == exp["source_url"]
        assert got.source_url_hash == url_hash(exp["source_url"])


# TC-1: every real row parses, and its keys come straight from its columns
def test_every_real_row_parses_and_keeps_its_columns() -> None:
    lines = _lines()
    assert len(lines) == 33
    for row_no, line in enumerate(lines):
        columns = line.split("\t")
        got = _parse(line, row_no)
        assert isinstance(got, CleanEvent), f"row {row_no}: {got}"
        assert got.event_id == int(columns[0])
        assert got.cameo_code == columns[26]
        assert got.num_mentions == int(columns[31])
        assert got.source_url_hash == url_hash(columns[60])


# TC-2: empty actors, geo and tone are normal
def test_empty_optional_fields_become_none() -> None:
    line = _lines()[0]
    for index in (5, 6, 7, 12):  # actor 1 is already empty in this row
        line = _with(line, index, "")
    for index in range(51, 59):  # action geo type..feature id
        line = _with(line, index, "")
    line = _with(line, 34, "")  # AvgTone
    line = _with(line, 30, "")  # GoldsteinScale
    got = _parse(line)
    assert isinstance(got, CleanEvent), got
    assert got.geo is None
    assert got.avg_tone is None
    assert got.goldstein is None
    assert got.actor1.model_dump() == {
        "code": None,
        "name": None,
        "country": None,
        "type1": None,
    }


# TC-2: a missing latitude keeps the rest of the place
def test_missing_lat_lon_keeps_the_place_name() -> None:
    line = _with(_with(_lines()[0], 56, ""), 57, "")
    got = _parse(line)
    assert isinstance(got, CleanEvent), got
    assert got.geo is not None
    assert got.geo.name == "Saint Thomas, Illinois, United States"
    assert got.geo.lat is None and got.geo.lon is None


# TC-5: bad rows land in the dead-letter with the expected reason and kind
@pytest.mark.parametrize("case", _load("bad_event_rows.json"), ids=lambda c: c["name"])
def test_bad_rows_are_dead_lettered(case: dict[str, Any]) -> None:
    got = _parse(case["line"], 7)
    assert isinstance(got, DlqMessage)
    assert got.reason == DlqReason(case["expect"])
    assert got.kind == "events"
    assert (got.slot, got.row_no) == (SLOT, 7)


def test_parser_never_raises_on_garbage() -> None:
    for line in ("", "\t" * 60, "x" * 5000, "\t".join(["a"] * 61)):
        assert isinstance(_parse(line), DlqMessage)
