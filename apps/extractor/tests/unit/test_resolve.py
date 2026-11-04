"""TC-6 (AC-3): the address guard refuses everything but public web addresses."""

import asyncio

import pytest
from newsdock_extractor.adapters.resolve import (
    AddressPolicy,
    Allowed,
    Refused,
    ResolveError,
    Unresolved,
    check_url_shape,
    guard,
)
from newsdock_extractor.config import Settings

PUBLIC = "93.184.216.34"


class FakeResolver:
    def __init__(self, table: dict[str, list[str]] | None = None) -> None:
        self.table = table or {}
        self.calls: list[str] = []

    async def resolve(self, host: str) -> list[str]:
        self.calls.append(host)
        if host not in self.table:
            raise ResolveError(host)
        return self.table[host]


def run_guard(
    url: str,
    table: dict[str, list[str]] | None = None,
    policy: AddressPolicy | None = None,
) -> tuple[object, FakeResolver]:
    resolver = FakeResolver(table)
    verdict = asyncio.run(guard(url, resolver, policy or AddressPolicy()))
    return verdict, resolver


REFUSED_LITERALS = [
    "127.0.0.1",
    "127.8.9.1",
    "10.0.0.5",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254",  # cloud metadata
    "100.64.0.1",  # carrier-grade NAT
    "0.0.0.0",
    "224.0.0.1",  # multicast (Python's `is_global` says True for it: T-06 finding)
    "239.255.255.250",
    "255.255.255.255",  # broadcast
    "240.0.0.1",  # reserved
    "192.0.2.1",  # documentation range
    "198.18.0.1",  # benchmarking range
    "::1",
    "fc00::1",
    "fd12:3456::1",
    "fe80::1",
    "ff02::1",  # IPv6 multicast
    "::ffff:127.0.0.1",  # IPv4-mapped loopback
    "::ffff:10.0.0.1",
    "::ffff:224.0.0.1",
    "::",
    # IPv6 transition prefixes that carry an IPv4 address
    "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
    "64:ff9b::a00:1",  # NAT64 of 10.0.0.1
    "2002:7f00:1::",  # 6to4 of 127.0.0.1
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
]


@pytest.mark.parametrize("address", REFUSED_LITERALS)
def test_literal_addresses_that_are_not_public_are_refused(address: str) -> None:
    host = f"[{address}]" if ":" in address else address
    verdict, resolver = run_guard(f"http://{host}/page")
    assert isinstance(verdict, Refused), (address, verdict)
    assert resolver.calls == []  # a literal needs no lookup


@pytest.mark.parametrize(
    ("host", "answers"),
    [
        ("localhost", ["127.0.0.1", "::1"]),
        ("postgres", ["172.18.0.2"]),  # compose service names resolve to private IPs
        ("kafka", ["172.18.0.3"]),
        ("host.docker.internal", ["192.168.65.254"]),
        ("metadata.internal", ["169.254.169.254"]),
        ("rebind.example", [PUBLIC, "10.0.0.1"]),  # every answer must be public
        ("mapped.example", ["::ffff:127.0.0.1"]),
    ],
)
def test_names_resolving_to_non_public_addresses_are_refused(
    host: str, answers: list[str]
) -> None:
    verdict, resolver = run_guard(f"https://{host}/page", {host: answers})
    assert isinstance(verdict, Refused), (host, verdict)
    assert resolver.calls == [host]


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pw@example.com/",  # credentials in the URL
        "http://user@example.com/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/",
        "javascript:alert(1)",
        "http:///nohost",
        "https://example.com:8080/",
        "http://example.com:22/",
        "http://example.com:99999/",
        "http://example.com:abc/",
        "//example.com/protocol-relative",
        "example.com/no-scheme",
        "",
    ],
)
def test_other_schemes_ports_and_credentials_are_refused_before_any_lookup(
    url: str,
) -> None:
    assert isinstance(check_url_shape(url), Refused), url
    verdict, resolver = run_guard(url, {"example.com": [PUBLIC]})
    assert isinstance(verdict, Refused)
    assert resolver.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a",
        "https://example.com/a",
        "http://example.com:80/a",
        "https://example.com:443/a",
        "https://Example.COM/A?x=1#frag",
    ],
)
def test_a_public_name_on_a_web_port_is_allowed_and_the_address_is_pinned(
    url: str,
) -> None:
    verdict, resolver = run_guard(
        url, {"example.com": [PUBLIC], "Example.COM": [PUBLIC]}
    )
    assert verdict == Allowed(address=PUBLIC)
    assert len(resolver.calls) == 1  # exactly one lookup: the answer is pinned


def test_the_first_public_address_is_the_one_to_connect_to() -> None:
    verdict, _ = run_guard(
        "https://multi.example/", {"multi.example": ["2606:2800:220:1::1", PUBLIC]}
    )
    assert verdict == Allowed(address="2606:2800:220:1::1")


def test_a_public_ipv6_literal_is_allowed() -> None:
    verdict, resolver = run_guard("https://[2606:2800:220:1::1]/x")
    assert verdict == Allowed(address="2606:2800:220:1::1")
    assert resolver.calls == []


def test_a_failed_or_empty_lookup_is_unresolved_not_refused() -> None:
    verdict, _ = run_guard("https://nowhere.example/")
    assert isinstance(verdict, Unresolved)
    verdict, _ = run_guard("https://empty.example/", {"empty.example": []})
    assert isinstance(verdict, Unresolved)


def test_an_address_with_a_zone_id_is_refused() -> None:
    verdict, _ = run_guard("https://zone.example/", {"zone.example": ["fe80::1%eth0"]})
    assert isinstance(verdict, Refused)


# the policy is strict by default and only the test constructor can loosen it
def test_loopback_is_allowed_only_when_the_policy_says_so_and_nothing_else_is() -> None:
    lax = AddressPolicy(allow_loopback=True)
    verdict, _ = run_guard("http://127.0.0.1/x", policy=lax)
    assert verdict == Allowed(address="127.0.0.1")
    for address in ("10.0.0.1", "169.254.169.254", "192.168.0.1", "::ffff:10.0.0.1"):
        host = f"[{address}]" if ":" in address else address
        refused, _ = run_guard(f"http://{host}/", policy=lax)
        assert isinstance(refused, Refused), address
    strict, _ = run_guard("http://127.0.0.1/x")
    assert isinstance(strict, Refused)
    assert AddressPolicy().allow_loopback is False


def test_no_setting_or_environment_variable_can_loosen_the_policy() -> None:
    assert not any(
        "loopback" in name or "private" in name for name in Settings.model_fields
    )


def test_the_policy_can_name_other_ports_for_tests_and_the_default_stays_80_443() -> (
    None
):
    assert AddressPolicy().allowed_ports == (80, 443)
    assert isinstance(check_url_shape("http://example.com:8123/"), Refused)
    named = AddressPolicy(allowed_ports=(8123,))
    assert check_url_shape("http://example.com:8123/", named) is None
    assert isinstance(check_url_shape("http://example.com:80/", named), Refused)
    assert isinstance(check_url_shape("http://example.com:81/", named), Refused)


def test_ports_cannot_be_set_from_a_setting_either() -> None:
    assert not any("port" in name.split("_") for name in Settings.model_fields)


def test_a_url_without_a_port_is_judged_by_its_default_port() -> None:
    only_8123 = AddressPolicy(allowed_ports=(8123,))
    assert isinstance(check_url_shape("http://example.com/", only_8123), Refused)  # 80
    assert isinstance(
        check_url_shape("https://example.com/", only_8123), Refused
    )  # 443
    assert check_url_shape("http://example.com/") is None
    assert check_url_shape("https://example.com/") is None
