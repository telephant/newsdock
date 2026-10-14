"""TC-16 (AC-2): subscription filter validation and its query form."""

import pytest
from newsdock_api.domain.subscriptions import (
    InvalidFilter,
    SubscriptionFilter,
    parse_filter,
    split_theme,
)

MAX = 20


def test_valid_filter_round_trips_and_gives_query_arguments() -> None:
    f = parse_filter({"theme": "ECON_*", "domain": "example.com", "text": "fed"}, MAX)
    assert f.as_query() == {"theme": "ECON_*", "domain": "example.com", "text": "fed"}
    assert f.as_json() == {"theme": "ECON_*", "domain": "example.com", "text": "fed"}


def test_empty_filter_is_allowed_and_matches_everything() -> None:
    f = parse_filter({}, MAX)
    assert f.as_query() == {"theme": None, "domain": None, "text": None}
    assert f.as_json() == {}


def test_omitted_fields_are_not_stored() -> None:
    assert parse_filter({"domain": "a.org"}, MAX).as_json() == {"domain": "a.org"}


@pytest.mark.parametrize(
    "raw",
    [
        {"unknown": "x"},  # extra=forbid
        {"theme": 5},  # not a string
        {"domain": ["a.org"]},
        {"text": "x" * (MAX + 1)},  # over-long
        {"theme": ""},  # empty string
        {"domain": "   "},
        {"theme": "ECON_*X"},  # '*' only as the last character
        {"theme": "*"},  # a bare '*' has no prefix
        {"theme": "A*B*"},
        {"theme": None, "extra": 1},
    ],
)
def test_invalid_filters_are_rejected(raw: dict[str, object]) -> None:
    with pytest.raises(InvalidFilter):
        parse_filter(raw, MAX)


def test_non_object_is_rejected() -> None:
    with pytest.raises(InvalidFilter):
        parse_filter(["theme"], MAX)


def test_split_theme_prefix_semantics() -> None:
    assert split_theme("ECON_*") == ("ECON_", True)
    assert split_theme("ECON_INFLATION") == ("ECON_INFLATION", False)


def test_model_is_frozen() -> None:
    f = SubscriptionFilter(theme="A")
    with pytest.raises(Exception):  # noqa: B017, PT011
        f.theme = "B"  # type: ignore[misc]
