"""TC-4 (parse_include), TC-9 (unit part), TC-17 (check_min_negativity): tone rules."""

import math

import pytest
from newsdock_api.domain.tone import (
    TONE_FIELDS,
    InvalidInclude,
    InvalidNegativity,
    check_min_negativity,
    parse_include,
)


def test_the_four_stored_tone_numbers_are_the_only_fields() -> None:
    assert TONE_FIELDS == ("tone", "tone_pos", "tone_neg", "tone_polarity")


@pytest.mark.parametrize("raw", [None, [], (), "", " , "])
def test_nothing_requested_gives_an_empty_tuple(raw: object) -> None:
    assert parse_include(raw) == ()  # type: ignore[arg-type]


def test_comma_string_list_and_duplicates_keep_first_order() -> None:
    assert parse_include("tone, tone_neg") == ("tone", "tone_neg")
    assert parse_include(["tone", "tone", "tone_neg"]) == ("tone", "tone_neg")
    assert parse_include(["tone_neg", "tone"]) == ("tone_neg", "tone")
    assert parse_include("tone_neg,tone_neg") == ("tone_neg",)


@pytest.mark.parametrize(
    "raw",
    [["tone_x"], "tone,word_count", ["title"], [""], ["Tone"], ["tone", "nope"]],
)
def test_unknown_or_empty_names_are_rejected(raw: object) -> None:
    with pytest.raises(InvalidInclude):
        parse_include(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [None, 0, 0.0, 8, 8.0, 9.7, 12.5, 100, 100.0])
def test_valid_negativity_is_returned_unchanged(value: float | None) -> None:
    assert check_min_negativity(value) == value


@pytest.mark.parametrize(
    "value",
    [-0.1, -1, 100.1, 101, math.nan, math.inf, -math.inf, True, False, "8", "abc"],
)
def test_bad_negativity_is_rejected(value: object) -> None:
    with pytest.raises(InvalidNegativity):
        check_min_negativity(value)  # type: ignore[arg-type]
