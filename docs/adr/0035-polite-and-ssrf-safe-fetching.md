# ADR-0035: Polite and SSRF-safe fetching

Status: **Accepted 2026-11-02** (spec `body-extraction`, D-3; confirmed by the user during `/spec-design`)

## Context
The owner chose "polite and bounded" (D-3): honest user agent, obey robots.txt, one request per site at a time with a delay, text capped, private use. Checked 2026-11-02 **[verified]**: of 40 sampled sites 9 disallow our agent, 5 declare a Crawl-delay of 1–20 s; Python's `urllib.robotparser` ignores wildcard and `$` rules (it wrongly allowed 3 of 6 test URLs) while `protego` 0.7.0 (released 2026-09-21) gets all six right; `httpcore` 1.0.9 can connect to a pinned IP while verifying TLS against the site's name (`sni_hostname`). URLs come from an untrusted feed, so the fetcher must not be steerable to internal addresses (SSRF), including by DNS rebinding and redirects.

## Options
- **(a) Protego robots, Crawl-delay honoured up to a cap, one article per site per round; resolve → require global addresses → connect to that address with the site's TLS name; redirects followed by hand and re-checked; ports 80/443; no cookies.**
- **(b) `urllib.robotparser` and a plain `httpx` client with `follow_redirects=True` and a "validate then fetch" check.** Simple, but wrong on wildcard rules and open to DNS rebinding and redirect-to-internal.
- **(c) An outbound proxy or egress firewall that enforces the address rules.** Strongest, needs infrastructure the project does not have; kept as a later hardening step.

## Decision
**(a)**.
- Robots: Protego, per-host cache (24 h), 401/403 = disallow all, other 4xx = allow all, 5xx or unreachable = disallow for now and retry later. `Crawl-delay` is honoured: delay = max(configured delay, Crawl-delay); above `max_crawl_delay_seconds` (30) the site is skipped as `blocked_robots` rather than crawled faster than it asks.
- Politeness: each round takes at most one article per site and only when that site's delay has elapsed; descriptive user agent; no cookies or credentials; `Accept-Language: en`.
- SSRF: scheme `http(s)`, no userinfo, ports 80 and 443 only; every resolved address must be `is_global`; connect to the validated address; manual redirects (max 3), each re-validated; response streamed with a byte cap (2 MB), a content-type check and connect/read/total timeouts. Certificate verification is never disabled.

## Consequences
+ Wildcard robots rules are respected; slow-crawl sites are not hammered; DNS rebinding and redirect tricks do not reach internal addresses. This guard is the only wall against SSRF, because the extractor shares the `data` network (ADR-0034), so it needs its own tests for every refused address class.
+ All limits are settings (ADR-0013) and provisional values are recorded in the spec.
− Sites with a Crawl-delay above the cap are never covered (in the sample none exceeded 20 s).
− Pinning to an IP needs a custom request path (rewritten URL, `Host` header, `sni_hostname`); a spike test must prove certificates are still verified, and a site that rotates addresses is only checked per request.
− Added at T-01 (2026-11-02): connections must never be reused across requests. A pooled connection to an IP is reused without re-checking the claimed name, which defeats certificate verification; the fetcher uses a new connection per request (one request per site every few seconds anyway).
− Added at T-01: HTTP 429 is treated as transient (retry later, honouring `Retry-After`), not as a refusal; 8 of 320 sampled URLs answered 429.
− Found at T-06 (2026-11-02): Python's `ipaddress.is_global` is not enough. It reports IPv4 multicast (`224.0.0.1`) and IPv6 multicast as global, and NAT64 (`64:ff9b::/96`) addresses can embed `127.0.0.1`. The guard therefore also checks `is_multicast`, `is_reserved`, `is_unspecified`, `is_link_local`, `is_loopback` and `is_private`, judges IPv4-mapped IPv6 addresses by their IPv4 part, and refuses the IPv6 transition prefixes that embed an IPv4 address (NAT64, 6to4, Teredo) outright.
− Only ports 80/443: a site on another port is `blocked_address`.
− Not a legal opinion: copyright and terms of use of the pages and of GDELT are the owner's call (spec risk).
