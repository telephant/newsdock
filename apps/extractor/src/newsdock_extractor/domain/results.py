"""What fetching one page can give back (the worker's input).

Defined in the domain so the worker does not import an adapter; `adapters.fetch`
re-uses these types. A `Fetched` is a page; a `FetchFailure` says whether the failure is
final (store the status), transient (retry later) or a wait for an unreachable
robots.txt.
"""

from dataclasses import dataclass
from enum import StrEnum

from newsdock_extractor.domain.status import BodyStatus


class FailureKind(StrEnum):
    final = "final"  # store `status` and stop
    transient = "transient"  # 429, 5xx, timeout, connection or certificate error
    robots_unreachable = "robots_unreachable"  # wait, do not count an attempt


@dataclass(frozen=True)
class Fetched:
    body: bytes  # the HTML, decoded from any content encoding
    final_url: str
    http_status: int
    wire_bytes: int  # bytes received on the wire (compressed)
    charset: str | None
    crawl_delay: float | None  # of the page's site, for the scheduler


@dataclass(frozen=True)
class FetchFailure:
    kind: FailureKind
    status: BodyStatus  # the status to store when final, `failed` when transient
    reason: str
    http_status: int | None = None
    retry_after_seconds: float | None = None
    crawl_delay: float | None = None
