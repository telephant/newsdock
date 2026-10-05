"""URL normalization: lower scheme/host, strip fragment and trailing /, keep query."""

from newsdock_core.urls import normalize_url, url_hash


def test_scheme_and_host_lowercased_path_kept() -> None:
    assert (
        normalize_url("HTTPS://Example.COM/News/Item")
        == "https://example.com/News/Item"
    )


def test_fragment_stripped_query_kept() -> None:
    assert (
        normalize_url("https://example.com/a?id=1&b=2#section")
        == "https://example.com/a?id=1&b=2"
    )


def test_trailing_slash_stripped() -> None:
    assert normalize_url("https://example.com/a/") == "https://example.com/a"
    assert normalize_url("https://example.com/") == "https://example.com"


def test_equivalent_urls_hash_identically() -> None:
    a = url_hash("HTTPS://Example.com/x/#top")
    b = url_hash("https://example.com/x")
    assert a == b and len(a) == 64 and int(a, 16) >= 0
