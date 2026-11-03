"""Body statuses (design-detail.md section 2). The names are fixed: they are stored in
`article_bodies.status` (a check constraint in migration 0012) and returned by the API.
"""

from enum import StrEnum


class BodyStatus(StrEnum):
    pending = "pending"  # queued, or waiting for a retry
    ok = "ok"  # text stored
    blocked_robots = "blocked_robots"  # robots.txt, or a Crawl-delay above the cap
    blocked_address = "blocked_address"  # scheme, port or address not allowed
    http_error = "http_error"  # 4xx (except 429), or a redirect without a target
    not_html = "not_html"  # content type is not HTML
    too_large = "too_large"  # body above the byte cap
    no_text = "no_text"  # nothing extracted, or fewer characters than the minimum
    failed = "failed"  # 429, 5xx, timeout or connection error, retries used up


FINAL_STATUSES: frozenset[BodyStatus] = frozenset(BodyStatus) - {BodyStatus.pending}
