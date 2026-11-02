"""TC-6 (AC-3, AC-4): title cleaning, tokens and the match rule."""

import pytest

from whathappen.domain.titles import MatchParams, clean_title, matches, title_tokens


# --- clean_title -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        (
            "Haley Stevens Removed From Michigan Party | News Radio 105.5 WERC",
            "Haley Stevens Removed From Michigan Party",
        ),
        (
            "Ashdon Jase Randall jailed | The Armidale Express",
            "Ashdon Jase Randall jailed",
        ),
        # a second segment goes only while 3+ words remain in front of it
        (
            "Letters | Opinion | Somerset County Gazette",
            "Letters | Opinion",
        ),
        (
            "Labour's latest scandal adds insult to injury | Politics | News",
            "Labour's latest scandal adds insult to injury",
        ),
        (
            "Visitors become stars as consumers spend more | WKZO | Kalamazoo",
            "Visitors become stars as consumers spend more",
        ),
        ("Short title | Section | Publisher", "Short title | Section"),  # 2 words left
        ("Plain headline", "Plain headline"),
        (
            "Price &#x2013; slide hits &#xA3;5",
            "Price – slide hits £5",
        ),  # entities decoded
        ("  Spaces \n  everywhere  ", "Spaces everywhere"),
    ],
)
def test_clean_title(raw: str, cleaned: str) -> None:
    assert clean_title(raw) == cleaned


def test_a_long_tail_after_the_pipe_is_not_an_outlet() -> None:
    long_tail = "x" * 61
    title = f"Real headline | {long_tail}"
    assert clean_title(title) == title


@pytest.mark.parametrize("raw", ["| The Armidale Express", "Only a segment | ", " | "])
def test_a_title_that_would_become_empty_is_left_alone(raw: str) -> None:
    assert clean_title(raw) == " ".join(raw.split())


# --- title_tokens ------------------------------------------------------------------
def test_tokens_are_lowercase_significant_truncated_words() -> None:
    tokens = title_tokens(
        "Connecticut Senator Chris Murphy is hospitalized with a stroke"
    )
    # "chris" becomes "chri": the plural fold is crude, but both sides fold alike
    assert tokens == {"connec", "senato", "chri", "murphy", "hospit", "stroke"}


def test_rewordings_share_their_key_tokens() -> None:
    a = title_tokens("Connecticut Senator Chris Murphy is hospitalized with a stroke")
    b = title_tokens("Senator Chris Murphy Hospitalized After Stroke")
    assert {"senato", "chri", "murphy", "hospit", "stroke"} <= a & b


def test_plurals_fold_and_stop_words_and_short_words_drop() -> None:
    assert title_tokens("The rates of cities and the 9 dead") == {
        "rate",
        "city",
        "dead",
    }
    assert title_tokens("It is a to be or not") == frozenset()


def test_long_words_are_cut_to_six_characters() -> None:
    assert title_tokens("hospitalised hospitalized hospital") == {"hospit"}


def test_the_outlet_suffix_is_not_part_of_the_tokens() -> None:
    with_suffix = title_tokens("Storm hits coast | News Radio 105.5 WERC")
    assert with_suffix == title_tokens("Storm hits coast")


def test_entities_and_punctuation_do_not_leak_into_tokens() -> None:
    assert title_tokens("Price&#x2014;slide: &#xA3;115bn (est.)") == {
        "price",
        "slide",
        "115bn",
        "est",
    }


# --- matches: the boundaries of both rules ------------------------------------------
def words(prefix: str, n: int) -> frozenset[str]:
    return frozenset(f"{prefix}{i}" for i in range(n))


def sets(
    shared: int, only_a: int, only_b: int
) -> tuple[frozenset[str], frozenset[str]]:
    common = words("c", shared)
    return common | words("a", only_a), common | words("b", only_b)


OVERLAP_ONLY = MatchParams(overlap=0.75, jaccard=1.1, min_shared=3)
JACCARD_ONLY = MatchParams(overlap=1.1, jaccard=0.5, min_shared=3)


def test_overlap_rule_at_and_below_the_boundary() -> None:
    a, b = sets(shared=3, only_a=1, only_b=5)  # |A|=4, |B|=8, overlap 3/4 = 0.75
    assert matches(a, b, OVERLAP_ONLY)
    a, b = sets(shared=3, only_a=2, only_b=5)  # |A|=5, overlap 3/5 = 0.60
    assert not matches(a, b, OVERLAP_ONLY)


def test_jaccard_rule_at_and_below_the_boundary() -> None:
    a, b = sets(shared=3, only_a=0, only_b=3)  # |A∪B|=6, Jaccard 3/6 = 0.50
    assert matches(a, b, JACCARD_ONLY)
    a, b = sets(shared=3, only_a=0, only_b=4)  # Jaccard 3/7 = 0.43
    assert not matches(a, b, JACCARD_ONLY)


def test_either_rule_is_enough_with_the_defaults() -> None:
    default = MatchParams()
    assert (default.overlap, default.jaccard, default.min_shared) == (0.75, 0.5, 3)
    a, b = sets(shared=3, only_a=1, only_b=5)  # overlap only
    assert matches(a, b, default)
    a, b = sets(shared=5, only_a=3, only_b=3)  # Jaccard 5/11=0.45, overlap 5/8=0.63
    assert not matches(a, b, default)


def test_two_shared_words_never_match_even_if_identical() -> None:
    a = frozenset({"alpha", "beta"})
    assert not matches(a, a, MatchParams())
    assert matches(
        frozenset({"alpha", "beta", "gamma"}),
        frozenset({"alpha", "beta", "gamma"}),
        MatchParams(),
    )


def test_empty_sets_do_not_match_and_do_not_divide_by_zero() -> None:
    assert not matches(frozenset(), frozenset(), MatchParams())
    assert not matches(frozenset(), words("a", 5), MatchParams())
