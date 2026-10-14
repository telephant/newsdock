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


# ---- M2a follow-up (ADR-0012 amendment 2026-10-09): same-domain look-alike guard --

from newsdock_core.stories import can_join, page_signature  # noqa: E402


def test_page_signature_ignores_scheme_host_port_and_fragment() -> None:
    a = page_signature("https://wtak.iheart.com/content/2026-10-08-aerosmith-are-back")
    b = page_signature(
        "http://937theriver.iheart.com:443/content/2026-10-08-aerosmith-are-back#x"
    )
    assert a == b


def test_page_signature_keeps_the_last_segment_and_the_query() -> None:
    assert page_signature("https://a.com/x/Story-One/") == ("story-one", "")
    assert page_signature("http://www.bellevision.com?action=topnews&type=28980") == (
        "",
        "action=topnews&type=28980",
    )
    # query order does not matter
    assert page_signature("https://a.com/p?b=2&a=1") == page_signature(
        "https://a.com/p?a=1&b=2"
    )


# Real copies seen on live GDELT slots (2026-10-08). Each tuple: (domain, url).
SAME_STORY_GROUPS = [
    # iHeart radio network: different station hosts, same slug
    [
        ("iheart.com", "https://wtak.iheart.com/content/2026-10-08-aerosmith-are-back"),
        (
            "iheart.com",
            "https://937theriver.iheart.com/content/2026-10-08-aerosmith-are-back",
        ),
    ],
    # same, but one station adds a path prefix
    [
        (
            "iheart.com",
            "https://wsrz.iheart.com/featured/florida-news/content/2026-10-08-gulf-on-alert",
        ),
        (
            "iheart.com",
            "https://1035thebeat.iheart.com/content/2026-10-08-gulf-on-alert",
        ),
    ],
    # one page under http and https
    [
        (
            "zfenglish.com",
            "http://www.zfenglish.com/companies/p-a-b-romania-s-former-metalwork-factory-sold-for-eur4-5m-23255915",
        ),
        (
            "zfenglish.com",
            "https://www.zfenglish.com/companies/p-a-b-romania-s-former-metalwork-factory-sold-for-eur4-5m-23255915",
        ),
    ],
    # syndication across different domains is always allowed
    [
        ("delcotimes.com", "https://www.delcotimes.com/2026/10/08/best-tumbling-mats/"),
        ("timescall.com", "https://www.timescall.com/2026/10/08/best-tumbling-mats-2/"),
    ],
]

# Different pages under one generic title on one domain: must NOT group.
LOOKALIKE_GROUPS = [
    [  # title = site name
        (
            "miamistudent.net",
            "https://www.miamistudent.net/staff/ada-lillie-worthington",
        ),
        ("miamistudent.net", "https://www.miamistudent.net/staff/alyssa-vasquez"),
    ],
    [  # paywall banner title
        (
            "townsvillebulletin.com.au",
            "https://www.townsvillebulletin.com.au/news/queensland/first-look-at-uptown-revamp/news-story/b226d5735bb3",
        ),
        (
            "townsvillebulletin.com.au",
            "https://www.townsvillebulletin.com.au/news/queensland/another-story/news-story/c9d3e1",
        ),
    ],
    [  # same path, query id differs
        ("bellevision.com", "http://www.bellevision.com?action=topnews&type=28980"),
        ("bellevision.com", "http://www.bellevision.com?action=topnews&type=28978"),
    ],
    [  # boilerplate "Company Announcement" title, different companies
        (
            "investegate.co.uk",
            "https://www.investegate.co.uk/announcement/rns/ithaca-energy--ith/director-pdmr-shareholding/9814059",
        ),
        (
            "investegate.co.uk",
            "https://www.investegate.co.uk/announcement/rns/howden-joinery-group--hwdn/director-pdmr-shareholding/9814001",
        ),
    ],
]


def test_real_syndication_copies_may_join() -> None:
    for group in SAME_STORY_GROUPS:
        first, *rest = group
        sources = [first]
        for copy in rest:
            assert can_join(copy[0], copy[1], sources), copy
            sources.append(copy)


def test_same_domain_lookalike_pages_may_not_join() -> None:
    for group in LOOKALIKE_GROUPS:
        first, second = group
        assert not can_join(second[0], second[1], [first]), second


def test_a_copy_from_a_new_domain_always_joins() -> None:
    sources = [("miamistudent.net", "https://www.miamistudent.net/staff/ada")]
    assert can_join("other.com", "https://other.com/whatever", sources)


def test_unknown_domain_joins() -> None:
    sources = [("a.com", "https://a.com/x")]
    assert can_join(None, "https://a.com/y", sources)
