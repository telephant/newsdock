"""TC-1: story_key normalization — table-driven, incl. thresholds and fixpoint."""

import pytest
from newsdock_core.stories import (
    MAX_SEGMENT,
    MIN_REMAINDER,
    story_key,
)

BASE = "central bank raises interest rates again"  # 40 chars ≥ MIN_REMAINDER


def test_constants_match_adr_0012() -> None:
    assert (MIN_REMAINDER, MAX_SEGMENT) == (25, 45)


@pytest.mark.parametrize(
    "variant",
    [
        "Central Bank RAISES interest rates again",
        "  central   bank\traises interest rates again ",
        f"{BASE} | Wilts and Gloucestershire Standard",
        f"{BASE} - BusinessWorld Online",
        f"{BASE} – Some Local Courier",
        f"{BASE} — The Example Gazette",
        f"{BASE} - Extra Part | Site Name",  # fixpoint: strips twice
    ],
)
def test_variants_of_one_story_share_a_key(variant: str) -> None:
    assert story_key(variant) == story_key(BASE) == BASE


def test_nfkc_fullwidth_folds() -> None:
    assert story_key("Ｆｅｄ ｒａｉｓｅｓ ｒａｔｅｓ ｔｏｄａｙ ａｇａｉｎ") == (
        "fed raises rates today again"
    )


def test_different_titles_get_different_keys() -> None:
    assert story_key(BASE) != story_key("inflation eases as energy prices fall")


# threshold boundaries (ADR-0012): remainder ≥ 25, segment ≤ 45
def test_short_remainder_is_not_stripped() -> None:
    short = "x" * (MIN_REMAINDER - 1)  # 24 chars
    title = f"{short} | Site"
    assert story_key(title) == f"{short} | site"  # suffix kept, only normalized


def test_remainder_at_threshold_is_stripped() -> None:
    exact = "y" * MIN_REMAINDER  # 25 chars
    assert story_key(f"{exact} | Site") == exact


def test_long_segment_is_not_stripped() -> None:
    seg = "z" * (MAX_SEGMENT + 1)  # 46 chars
    title = f"{BASE} | {seg}"
    assert story_key(title) == title.lower()


def test_segment_at_threshold_is_stripped() -> None:
    seg = "z" * MAX_SEGMENT  # 45 chars
    assert story_key(f"{BASE} | {seg}") == BASE


def test_in_word_hyphens_never_strip() -> None:
    title = "well-known analyst covers state-owned enterprises"
    assert story_key(title) == title


def test_empty_and_whitespace_are_safe() -> None:
    assert story_key("") == ""
    assert story_key("   \t ") == ""
