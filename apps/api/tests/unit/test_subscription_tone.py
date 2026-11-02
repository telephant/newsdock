"""TC-15 (AC-12) and TC-17 (AC-13, subscription part): `min_negativity` in the saved
filter: parsing, storage form, old filters, and rejected values."""

import math

import pytest
from newsdock_api.domain.subscriptions import (
    InvalidFilter,
    SubscriptionRecord,
    parse_filter,
)

MAX = 20


def test_a_number_is_accepted_and_kept_as_a_number() -> None:
    f = parse_filter({"min_negativity": 8}, MAX)
    assert f.min_negativity == 8
    assert f.as_json() == {"min_negativity": 8}
    assert isinstance(f.as_json()["min_negativity"], float | int)
    assert f.as_query() == {
        "theme": None, "domain": None, "text": None, "min_negativity": 8,
    }  # fmt: skip


def test_it_combines_with_the_other_fields() -> None:
    f = parse_filter({"min_negativity": 8.5, "theme": "ECON_*", "domain": "a.org"}, MAX)
    assert f.as_json() == {"theme": "ECON_*", "domain": "a.org", "min_negativity": 8.5}
    assert f.as_query()["min_negativity"] == 8.5


def test_edges_zero_and_one_hundred_are_valid() -> None:
    assert parse_filter({"min_negativity": 0}, MAX).as_json() == {"min_negativity": 0}
    assert parse_filter({"min_negativity": 100}, MAX).min_negativity == 100


def test_omitted_or_null_is_not_stored() -> None:
    assert parse_filter({}, MAX).as_json() == {}
    assert parse_filter({"min_negativity": None}, MAX).as_json() == {}
    assert parse_filter({}, MAX).as_query()["min_negativity"] is None


def test_a_filter_saved_before_the_change_parses_and_serializes_the_same() -> None:
    old = {"theme": "ECON_*", "domain": "example.com", "text": "fed"}
    f = parse_filter(old, MAX)
    assert f.as_json() == old
    assert f.min_negativity is None


@pytest.mark.parametrize(
    "value",
    [
        -0.1,
        -1,
        100.1,
        101,
        math.nan,
        math.inf,
        -math.inf,
        True,
        False,
        "8",
        "",
        [8],
        {},
    ],
)
def test_bad_values_are_rejected(value: object) -> None:
    with pytest.raises(InvalidFilter):
        parse_filter({"min_negativity": value}, MAX)


def test_other_unknown_keys_are_still_rejected() -> None:
    with pytest.raises(InvalidFilter):
        parse_filter({"min_negativity": 8, "max_negativity": 20}, MAX)


def test_records_hold_numbers_next_to_strings() -> None:
    from datetime import UTC, datetime

    record = SubscriptionRecord(
        id="s1", agent_id="a1",
        filter={"theme": "ECON_*", "min_negativity": 8.5},
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
    )  # fmt: skip
    assert record.filter["min_negativity"] == 8.5
    assert record.model_dump(mode="json")["filter"]["min_negativity"] == 8.5
