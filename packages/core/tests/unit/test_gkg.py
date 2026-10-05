"""TC-7, TC-8, TC-10, TC-11: GKG row parsing against real fixture data."""

import json
from pathlib import Path
from typing import Any

import pytest
from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
from newsdock_core.gkg import parse_row

FIXTURES = Path(__file__).parent.parent / "fixtures"
SLOT = "20261004081500"


def _sample_lines() -> list[str]:
    return (FIXTURES / "gkg_sample.tsv").read_text().splitlines()


def _expected() -> list[dict[str, Any]]:
    with (FIXTURES / "expected_articles.json").open() as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


def _bad_rows() -> list[dict[str, Any]]:
    with (FIXTURES / "bad_rows.json").open() as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


# TC-10: ~20 real rows parse to the expected field values
def test_real_fixture_parses_to_expected_values() -> None:
    lines, expected = _sample_lines(), _expected()
    assert len(lines) == len(expected) == 20
    for row_no, (line, exp) in enumerate(zip(lines, expected, strict=True)):
        got = parse_row(slot=SLOT, row_no=row_no, line=line)
        assert isinstance(got, CleanArticle), f"row {row_no}: {got}"
        assert got.url_hash == exp["url_hash"]
        assert got.gkg_record_id == exp["gkg_record_id"]
        assert got.slot == SLOT
        assert got.url == exp["url"]
        assert got.title == exp["title"]
        assert got.domain == exp["domain"]
        assert got.published_at.isoformat() == exp["published_at"]
        assert got.themes == exp["themes"]
        assert got.persons == exp["persons"]
        assert got.orgs == exp["orgs"]
        assert got.tone.model_dump() == exp["tone"]


# TC-10: precise timestamp used when present, col 2 when absent
def test_published_at_fallback_rows_exist_in_fixture() -> None:
    results = [
        parse_row(slot=SLOT, row_no=i, line=line)
        for i, line in enumerate(_sample_lines())
    ]
    slot_time = {
        r.published_at.isoformat() for r in results if isinstance(r, CleanArticle)
    }
    # fixture contains both precise timestamps and col-2 fallbacks (slot time)
    assert "2026-10-04T08:15:00+00:00" in slot_time
    assert any(t != "2026-10-04T08:15:00+00:00" for t in slot_time)


# TC-7: missing URL / missing title → dlq with the right reason
@pytest.mark.parametrize(
    "name,reason",
    [
        ("missing_url", DlqReason.missing_url),
        ("no_title_tag", DlqReason.missing_title),
        ("empty_title", DlqReason.missing_title),
    ],
)
def test_bad_rows_route_to_dlq_with_reason(name: str, reason: DlqReason) -> None:
    row = next(b for b in _bad_rows() if b["name"] == name)
    got = parse_row(slot=SLOT, row_no=1, line=row["line"])
    assert isinstance(got, DlqMessage)
    assert got.reason == reason
    assert got.slot == SLOT and got.row_no == 1


# TC-8: wrong column count → bad_column_count; dlq line truncated to ≤ 2 KB
@pytest.mark.parametrize("name", ["cols_26", "cols_28"])
def test_wrong_column_count(name: str) -> None:
    row = next(b for b in _bad_rows() if b["name"] == name)
    got = parse_row(slot=SLOT, row_no=2, line=row["line"])
    assert isinstance(got, DlqMessage)
    assert got.reason == DlqReason.bad_column_count


def test_dlq_line_truncated_to_2kb() -> None:
    row = next(b for b in _bad_rows() if b["name"] == "huge_line_missing_url")
    assert len(row["line"]) > 2048
    got = parse_row(slot=SLOT, row_no=3, line=row["line"])
    assert isinstance(got, DlqMessage)
    assert len(got.line) <= 2048


# TC-11: empty themes/persons/orgs and empty domain are NOT errors
def test_empty_enrichment_fields_are_normal() -> None:
    empties = [
        e for e in _expected() if not e["themes"] or not e["persons"] or not e["orgs"]
    ]
    assert empties, "fixture must contain rows with empty enrichment fields"
    for row_no, line in enumerate(_sample_lines()):
        got = parse_row(slot=SLOT, row_no=row_no, line=line)
        assert isinstance(got, CleanArticle)


def test_empty_domain_is_null_not_error() -> None:
    row = next(b for b in _bad_rows() if b["name"] == "empty_domain_parses_clean")
    got = parse_row(slot=SLOT, row_no=4, line=row["line"])
    assert isinstance(got, CleanArticle)
    assert got.domain is None


def test_nul_byte_title_parses_clean() -> None:
    # Postgres will reject it later (sink poison, TC-31); the processor must not
    row = next(b for b in _bad_rows() if b["name"] == "nul_title_parses_clean")
    got = parse_row(slot=SLOT, row_no=5, line=row["line"])
    assert isinstance(got, CleanArticle)
    assert "\x00" in got.title
