"""TC-3, TC-4, TC-5 (mentions part): Mentions row parsing against real fixture data."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from newsdock_core.contracts import CleanMention, DlqMessage, DlqReason
from newsdock_core.mentions import parse_mention_row
from newsdock_core.urls import url_hash

FIXTURES = Path(__file__).parent.parent / "fixtures"
SLOT = "20261102110000"


def _lines() -> list[str]:
    return (FIXTURES / "mentions_sample.tsv").read_text().splitlines()


def _load(name: str) -> list[dict[str, Any]]:
    with (FIXTURES / name).open() as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


def _parse(line: str, row_no: int = 0) -> CleanMention | DlqMessage:
    return parse_mention_row(slot=SLOT, row_no=row_no, line=line)


# TC-3: hand-checked rows equal the expected values
def test_hand_checked_rows_parse_to_expected_values() -> None:
    lines = _lines()
    for exp in _load("expected_mentions.json"):
        got = _parse(lines[exp["row_no"]], exp["row_no"])
        assert isinstance(got, CleanMention), got
        assert got.event_id == exp["event_id"]
        assert got.url == exp["url"]
        assert got.url_hash == url_hash(exp["url"])
        assert got.source_name == exp["source_name"]
        assert got.mention_time == datetime(2026, 11, 2, 11, 0, tzinfo=UTC)
        assert got.confidence == exp["confidence"]


# TC-3: every real row parses; the repeated pair yields the same key twice
def test_every_real_row_parses_and_the_repeated_pair_has_one_key() -> None:
    lines = _lines()
    assert len(lines) == 60
    parsed = [_parse(line, n) for n, line in enumerate(lines)]
    assert all(isinstance(p, CleanMention) for p in parsed)
    keys = [(p.event_id, p.url_hash) for p in parsed if isinstance(p, CleanMention)]
    assert keys[0] == keys[1]
    assert len(set(keys)) == len(keys) - 1


# TC-4: an empty confidence is None (no real row has one; hand-made)
def test_empty_confidence_is_none() -> None:
    columns = _lines()[0].split("\t")
    columns[11] = ""
    got = _parse("\t".join(columns))
    assert isinstance(got, CleanMention), got
    assert got.confidence is None


# TC-5: bad rows land in the dead-letter with the expected reason and kind
@pytest.mark.parametrize(
    "case", _load("bad_mention_rows.json"), ids=lambda c: c["name"]
)
def test_bad_rows_are_dead_lettered(case: dict[str, Any]) -> None:
    got = _parse(case["line"], 3)
    assert isinstance(got, DlqMessage)
    assert got.reason == DlqReason(case["expect"])
    assert got.kind == "mentions"
    assert (got.slot, got.row_no) == (SLOT, 3)


def test_parser_never_raises_on_garbage() -> None:
    for line in ("", "\t" * 15, "x" * 5000, "\t".join(["a"] * 16)):
        assert isinstance(_parse(line), DlqMessage)
