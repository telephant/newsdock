"""The address guard (ADR-0035): only public web addresses are ever requested.

Steps: the URL must be `http(s)` with a host, no credentials and no port but 80/443;
the host is resolved by us (a literal address needs no lookup); every address must be
public (`is_global`), which refuses loopback, private, link-local, metadata
(169.254.169.254), carrier-grade NAT, multicast, reserved, documentation ranges, IPv4
mapped addresses of those, and the compose service names (they resolve to private
addresses). The first valid address is then pinned: the fetcher connects to exactly it,
so a second DNS answer cannot redirect the request.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

# IPv6 ranges that embed an IPv4 address (NAT64 well-known and local-use prefixes, 6to4,
# Teredo): refused outright rather than judged, news sites do not use them
_EMBEDDED_IPV4_NETWORKS = tuple(
    ipaddress.IPv6Network(net)
    for net in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32")
)


class ResolveError(Exception):
    """The name could not be resolved (a transient failure, not a refusal)."""


class Resolver(Protocol):
    async def resolve(self, host: str) -> list[str]: ...


class SystemResolver:
    """`getaddrinfo` in the event loop's executor; each answer address once."""

    async def resolve(self, host: str) -> list[str]:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise ResolveError(host) from exc
        seen: dict[str, None] = {}
        for info in infos:
            seen.setdefault(str(info[4][0]), None)
        return list(seen)


@dataclass(frozen=True)
class AddressPolicy:
    """Strict by default. `allow_loopback` and `allowed_ports` exist only so tests can
    reach a local server on its own port; they are constructor arguments, never a
    setting or an environment variable. Loopback is the only non-public range they
    open (private, link-local and the rest stay refused); a port not listed stays
    refused, so a redirect to another local port is still refused."""

    allow_loopback: bool = False
    allowed_ports: tuple[int, ...] = ALLOWED_PORTS


@dataclass(frozen=True)
class Allowed:
    address: str  # the address to connect to


@dataclass(frozen=True)
class Refused:
    reason: str  # becomes the status `blocked_address`


@dataclass(frozen=True)
class Unresolved:
    reason: str  # a lookup failure: transient, retried like a timeout


Verdict = Allowed | Refused | Unresolved


def check_url_shape(url: str, policy: AddressPolicy | None = None) -> Refused | None:
    """Scheme, host, credentials and port, before any lookup."""
    allowed_ports = (policy or AddressPolicy()).allowed_ports
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return Refused("malformed URL or port")
    if parts.scheme not in ALLOWED_SCHEMES:
        return Refused(f"scheme {parts.scheme!r} not allowed")
    if not parts.hostname:
        return Refused("no host")
    if parts.username is not None or parts.password is not None:
        return Refused("credentials in the URL")
    effective = port if port is not None else (443 if parts.scheme == "https" else 80)
    if effective not in allowed_ports:  # the default port counts as well
        return Refused(f"port {effective} not allowed")
    return None


def _public(address: str, policy: AddressPolicy) -> str | None:
    """The canonical address when it may be requested, else None."""
    if "%" in address:  # zone ids make no sense for a public address
        return None
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed.ipv4_mapped is not None:
            parsed = parsed.ipv4_mapped  # judge `::ffff:10.0.0.1` as 10.0.0.1
        elif any(parsed in net for net in _EMBEDDED_IPV4_NETWORKS):
            return None  # NAT64 and 6to4 carry an IPv4 address we would have to judge
    if policy.allow_loopback and parsed.is_loopback:
        return parsed.compressed
    # `is_global` alone is not enough: Python reports IPv4 and IPv6 multicast as global
    if (
        not parsed.is_global
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
        or parsed.is_link_local
        or parsed.is_loopback
        or parsed.is_private
    ):
        return None
    return parsed.compressed


def check_addresses(addresses: list[str], policy: AddressPolicy) -> Verdict:
    """Allowed only if there is an answer and every address is public."""
    if not addresses:
        return Unresolved("no address")
    checked = [_public(address, policy) for address in addresses]
    if any(address is None for address in checked):
        return Refused("resolves to a non-public address")
    return Allowed(address=str(checked[0]))


async def guard(url: str, resolver: Resolver, policy: AddressPolicy) -> Verdict:
    """The verdict for one URL; resolves at most once."""
    refused = check_url_shape(url, policy)
    if refused is not None:
        return refused
    host = urlsplit(url).hostname or ""
    try:
        ipaddress.ip_address(host)
        addresses = [host]  # a literal address: no lookup
    except ValueError:
        try:
            addresses = await resolver.resolve(host)
        except ResolveError:
            return Unresolved(f"could not resolve {host}")
    return check_addresses(addresses, policy)
