"""TC-9, TC-10 (AC-4, AC-5): main text of synthetic news pages, capped, or `no_text`."""

from pathlib import Path

import pytest
from newsdock_extractor.domain.extract import cap_text, extract_text
from newsdock_extractor.domain.status import BodyStatus

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
URL = "https://example.test/news/central-bank"
MARKERS = (
    "SITE-NAV-MARKER",
    "COOKIE-BANNER-MARKER",
    "AD-MARKER",
    "RELATED-MARKER",
    "FOOTER-MARKER",
)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def long_page(paragraphs: int, size: int = 700) -> tuple[str, list[str]]:
    """A synthetic article of many distinct paragraphs, and the paragraphs."""
    bodies = [
        f"Paragraph number {n} of the synthetic report. "
        + ("The committee reviewed the figures and noted steady progress. " * 20)[
            : size - 60
        ]
        for n in range(paragraphs)
    ]
    html = (
        "<!doctype html><html><head><title>Long report</title></head><body>"
        "<nav><a href='/'>Home</a></nav><main><article><h1>Long report</h1>"
        + "".join(f"<p>{p}</p>" for p in bodies)
        + "</article></main><footer>Copyright</footer></body></html>"
    )
    return html, bodies


# TC-9: the main text without navigation, banners, ads or footers
def test_news_page_gives_the_main_text_and_none_of_the_boilerplate() -> None:
    result = extract_text(
        fixture("news_page.html"), URL, min_chars=200, text_cap_chars=20_000
    )
    assert result.status is BodyStatus.ok
    assert result.text is not None
    for phrase in (
        "left its main interest rate unchanged on Thursday",
        "Governor Alex Sample told reporters",
        "Patience is the message",
        "quarterly report on financial stability",
    ):
        assert phrase in result.text
    for marker in MARKERS:
        assert marker not in result.text
    assert result.text == result.text.strip()


def test_text_over_the_cap_is_cut_at_a_paragraph_boundary() -> None:
    html, bodies = long_page(paragraphs=60)
    result = extract_text(html, URL, min_chars=200, text_cap_chars=20_000)
    assert result.status is BodyStatus.ok and result.text is not None
    assert 15_000 < len(result.text) <= 20_000
    kept = result.text.split("\n")
    assert kept[-1] in bodies  # ends on a whole paragraph, not in the middle of one
    assert bodies[0] in kept and bodies[-1] not in kept


def test_the_cap_is_a_parameter() -> None:
    result = extract_text(
        fixture("news_page.html"), URL, min_chars=50, text_cap_chars=600
    )
    assert result.text is not None and len(result.text) <= 600
    assert result.text.endswith(".") or result.text.endswith('"')


# TC-10: pages with nothing worth keeping
@pytest.mark.parametrize("name", ["stub_page.html", "non_article.html"])
def test_stubs_and_link_lists_are_no_text(name: str) -> None:
    result = extract_text(fixture(name), URL, min_chars=200, text_cap_chars=20_000)
    assert result.status is BodyStatus.no_text
    assert result.text is None


def test_min_chars_is_the_threshold() -> None:
    page = fixture("news_page.html")
    assert (
        extract_text(page, URL, min_chars=200, text_cap_chars=20_000).status
        is BodyStatus.ok
    )
    assert (
        extract_text(page, URL, min_chars=5_000, text_cap_chars=20_000).status
        is BodyStatus.no_text
    )


@pytest.mark.parametrize(
    "html",
    ["", "   ", "<html></html>", "not html at all", "\x00\x01\x02", "<p>" * 5000],
)
def test_garbage_never_raises(html: str) -> None:
    result = extract_text(html, URL, min_chars=200, text_cap_chars=20_000)
    assert result.status is BodyStatus.no_text and result.text is None


# the cap helper on its own
def test_cap_text_keeps_whole_paragraphs() -> None:
    text = "\n".join(["a" * 100] * 10)
    capped = cap_text(text, 350)
    assert capped == "\n".join(["a" * 100] * 3)  # 3 paragraphs + 2 separators = 302


def test_cap_text_below_the_cap_is_unchanged() -> None:
    assert cap_text("one\ntwo", 100) == "one\ntwo"


def test_cap_text_cuts_a_single_huge_paragraph_at_a_space() -> None:
    text = " ".join(["word"] * 100)  # 499 characters
    capped = cap_text(text, 100)
    assert len(capped) <= 100 and not capped.endswith(" ")
    assert capped.split(" ")[-1] == "word"  # no word cut in half


def test_cap_text_cuts_an_unbroken_run_hard() -> None:
    assert cap_text("x" * 1000, 100) == "x" * 100
