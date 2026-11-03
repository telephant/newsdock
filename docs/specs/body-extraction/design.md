# Design — body-extraction (M3d)

Spec: [spec.md](spec.md). Detail (not required for approval): [design-detail.md](design-detail.md). Diagrams: [diagrams/index.html](diagrams/index.html). Decisions (all Accepted 2026-11-02): [ADR-0034](../../adr/0034-extractor-app-on-the-data-network.md), [ADR-0035](../../adr/0035-polite-and-ssrf-safe-fetching.md), [ADR-0036](../../adr/0036-bodies-and-passages-tables-halfvec-and-a-discovery-queue.md), [ADR-0037](../../adr/0037-semantic-search-scope-titles-body-all.md).

Reading order: this file → diagrams → the four ADRs. Code facts were read from the repo on 2026-11-02 **[verified]**; data facts are in spec §3 and the checks below.

## Idea in five lines

1. A new worker `extractor` finds new canonical articles (a discovery pass fills a queue table), takes the newest first, and fetches one page per site per round.
2. Each fetch is polite (Protego robots.txt incl. wildcards and Crawl-delay, honest agent) and safe (resolve, check the address is public, connect to exactly that address, redirects re-checked).
3. `trafilatura` extracts the text; it is capped at 20,000 characters, stored in `article_bodies` with a status, and split into ~1,000-character passages in `article_passages`.
4. The existing embedder gets a second pass that embeds passages (stored as `halfvec(768)`), same model and client.
5. The API serves `body` and gains `semantic_search(scope = titles | body | all)`, fusing title legs and passage legs by reciprocal rank.

## Components

| Id | Job | Notes |
|---|---|---|
| C-80 | `extractor` app | Loop, per-site scheduler, queue discovery, retention-aware picking; the only component that talks to the open web |
| C-81 | Fetcher (adapter) | Protego robots cache, SSRF guard with a pinned address, manual redirects, size/time caps, no cookies |
| C-82 | Extraction and splitting (domain) | `trafilatura` call, text cap, passage splitter (pure functions) |
| C-83 | `article_bodies` | One row per canonical article: status, text, attempts; the queue is `status = 'pending'` |
| C-84 | `article_passages` | Passages with `halfvec(768)` vector, HNSW cosine, full-text index; cascade from `articles` |
| C-85 | Embedder, second pass | Embeds passages with no vector; same loop, skip list and backoff |
| C-86 | API | `body`/`body_status` on the detail, `include=body`, `scope` on `semantic_search`, passage legs |
| C-87 | Compose service | Service `extractor` (profile `apps`, heartbeat healthcheck) on the existing `data` network, no dependency on Kafka |

C-35/C-37/C-38 (embedder, search) and C-6 (API) are extended, not replaced. The ingester, processor and sink are not touched.

## Key flows

- **F-9 discover** — extractor inserts `pending` rows for articles above its cursor (diagram 2).
- **F-10 fetch and store** — pick, check robots, fetch, extract, write body and passages in one transaction (diagram 2).
- **F-11 embed passages** — embedder second pass fills vectors (diagram 2).
- **F-12 search** — `scope` picks the legs, fusion by rank, best passage per article (diagram 2).
- **F-13 retention** — deleting an article cascades to its body and passages (existing hourly job).

## Contracts

| Table | Key | Written by | Notes |
|---|---|---|---|
| `article_bodies` | `url_hash` (FK → `articles`, cascade) | extractor | `seq`, `status`, `text`, `http_status`, `attempts`, `next_attempt_at`, `fetched_at`; partial index on `seq` where pending |
| `article_passages` | `(url_hash, idx)` (FK → `articles`, cascade) | extractor (rows), embedder (vector) | `text`, `embedding halfvec(768)`, `embedding_model`; HNSW cosine, GIN full-text, partial index where no vector |

Body statuses (fixed names): `pending`, `ok`, `blocked_robots`, `blocked_address`, `http_error`, `not_html`, `too_large`, `no_text`, `failed`.

API additions: detail `body: str|null`, `body_status` (`none` if the article has no row); `include=body` on the four list surfaces; `semantic_search(scope)` with `invalid_scope`; results of `body`/`all` carry `passage` and `matched_by` values `body_vector`, `body_keyword` next to `vector`, `keyword`.

## Tricky parts

- **Queue without scanning.** A partial index on pending rows (like the embedder's) keeps polling cheap however many articles exist; pending rows are created by the extractor's own discovery pass from `articles.seq`, not by a trigger or the sink (ADR-0036).
- **Politeness by construction.** Each round takes at most one article per site and only for sites whose delay has elapsed; Crawl-delay above a cap means the site is skipped, not hammered (ADR-0035). In the 40-site sample 5 sites declared 1–20 s.
- **SSRF.** Names are resolved by us, every address must be global, the connection goes to that address with the site's TLS name, redirects are followed by hand and re-checked, only ports 80/443 (ADR-0035). The extractor shares the `data` network with Kafka and the workers (ADR-0034, the owner's choice), so this guard is the only wall: compose service names resolve to private addresses and are refused.
- **Storage.** Measured: 4.9 KB per passage with `halfvec` (text, HNSW, full-text and key included; 9.4 KB with `vector`), mean 4.7 passages per usable article, so 7 days is about 6–8.5 GB for the passages table (T-01).
- **Old and failing rows.** Pending rows older than the retention window are never picked (D-6) and vanish with their article; transient failures retry up to 3 times with growing delays, then `failed`.

## Failure modes (top)

| Failure | Effect | Handling |
|---|---|---|
| Site slow, blocking or erroring | that article ends with a status; others go on | per-site schedule, bounded retries |
| Extractor down or behind | bodies lag; search of titles, ingestion, `get_article` unaffected | AC-15; newest first, nothing older than 7 days |
| Ollama down | passages stay without vectors | embedder backoff as for titles; `degraded` in search |
| Page is huge or not HTML | refused early | size cap, content-type check |
| Embedding model changed | passage vectors cleared and re-embedded | same rule as titles |

## Technology

`httpx` (already used), `trafilatura` 2.3.1 and `protego` 0.7.0 (new, both released in 2026-09/10 **[verified]**), pgvector 0.8.7 with `halfvec` (image and Python package both support it **[verified]**), existing embedder, Alembic, FastAPI. A passage splitter of our own (no library).

## AC coverage

| AC | Component / flow |
|---|---|
| AC-1, AC-2 | C-81, C-80 (robots, per-site schedule) |
| AC-3 | C-81 (address guard) |
| AC-4 | C-82 (extraction, cap) |
| AC-5 | C-80, C-81 (status mapping, retries) |
| AC-6, AC-7 | C-80, C-83 (queue, discovery, picking), F-9, F-10 |
| AC-8 | C-83, C-84 cascade, F-13 |
| AC-9, AC-10 | C-86 (`body`, `include=body`) |
| AC-11 | C-82 (splitter), C-85, C-84 |
| AC-12, AC-13, AC-14 | C-86 (scopes, legs, fusion, degraded), F-12 |
| AC-15 | C-80/C-85 independence (no change to ingestion or the API's outbound traffic), C-87 |
| AC-16 | all, on the dev stack (manual) |

## Questions to answer before approving this design

All answered 2026-11-02:

- [x] A separate app `extractor`: accepted, but on the existing `data` network, not the recommended `crawl` network (ADR-0034). The address guard is the only wall against SSRF; a `crawl` network stays a hardening option in the backlog.
- [x] Crawl-delay honoured with a 30 s cap, sites above it skipped as `blocked_robots`; one page per site per round; SSRF guard with a pinned address: accepted (ADR-0035).
- [x] `halfvec(768)` passage vectors: accepted (ADR-0036).
- [x] The extractor creates its own queue rows by watching `articles.seq`, last 6 hours on first run, no back-fill, no trigger, no sink change: accepted (ADR-0036).
- [x] `scope` = `titles` | `body` | `all`, default `titles` with a setting to flip it, four legs fused by rank: accepted (ADR-0037).
- [x] ADR-0034 (changed to option b), ADR-0035, ADR-0036 and ADR-0037: Accepted 2026-11-02.
