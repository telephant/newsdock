# ADR-0034: A separate `extractor` app on the existing `data` network

Status: **Accepted 2026-11-02** (spec `body-extraction`; the owner chose option (b) at `/spec-design`, not the recommended (a))

## Context
Body extraction fetches web pages chosen by third parties (the URLs come from GDELT). It is the first component that talks to arbitrary hosts. Today the ingester fetches one fixed host (`data.gdeltproject.org`), the embedder and API reach only the host's Ollama. Compose has two networks, `data` (Postgres, Kafka, workers) and `agent`; the check that isolates the agent only probes Postgres and Kafka, and nothing restricts egress (found 2026-11-02 **[verified]**). A new app folder needs an ADR (ADR-0005 counted five Python apps, ADR-0006 requires one for rule changes; the embedder got ADR-0024).

## Options
- **(a) New app `extractor` on a new network `crawl` shared only with Postgres.** The worker reaches the open web and the database, nothing else. (Recommended, not chosen.)
- **(b) New app on the existing `data` network.** Same process isolation, fewer compose changes; it can reach Kafka and every worker by name.
- **(c) A second loop inside the embedder app.** Fewer containers; mixes the only web-facing code with a worker that holds an Ollama link and breaks the "one deployable per folder" rule.
- **(d) The API fetches pages on demand.** No new app; the API (which agents reach) would make outbound requests to arbitrary hosts.

## Decision
**(b)**: `apps/extractor` (own Dockerfile, `pyproject`, settings section, heartbeat healthcheck), service `extractor` on the existing network `data`, no dependency on Kafka. It imports only `packages/*` (`newsdock_config`, `newsdock_db`) and never another app.

## Consequences
+ No new network and no change to the Postgres service or to the isolation test's network checks; one container and one image more.
+ The API stays free of outbound fetching (AC-15); failure and restarts of the extractor are independent of ingestion.
− **The extractor shares a network with Kafka and the workers.** The only wall against server-side request forgery is the address guard in the fetcher (ADR-0035): every resolved address must be public, which refuses the compose service names (they resolve to private addresses), `host.docker.internal`, loopback and metadata addresses, and redirects are re-checked. A compromised extractor process (for example through a parser bug on a hostile page) could still connect to Kafka or Postgres directly. The `crawl` network would have limited that; it stays an option (backlog, hardening).
− The app-enumerating tooling (layout check, import-linter contracts, CI matrix, isolation test's exact service list, `check_config`) must all learn about the new app.
− The compose stack connects services as the database superuser (existing, not changed here), so the narrow `extractor_rw` grants document intent and are not enforced yet.
