# Design detail — body-extraction

Reference only; not required reading to approve the design. Summary: [design.md](design.md).

## 1. Schema (migration `0012_article_bodies`, additive, forward-only)

```
article_bodies(
  url_hash text PK REFERENCES articles(url_hash) ON DELETE CASCADE,
  seq bigint NOT NULL,                 -- copy of articles.seq, newest-first ordering and the discovery cursor
  status text NOT NULL DEFAULT 'pending',
  text text,                           -- cleaned main text, at most extractor.text_cap_chars
  http_status smallint,                -- last HTTP status seen, for http_error and diagnosis
  attempts smallint NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  fetched_at timestamptz,
  CHECK (status IN ('pending','ok','blocked_robots','blocked_address','http_error',
                    'not_html','too_large','no_text','failed')))   -- names fixed in §2
  idx ix_article_bodies_seq (seq)                                  -- discovery cursor: max(seq)
  idx ix_article_bodies_pending (seq) WHERE status = 'pending'      -- the queue, read newest first (backward scan)
article_passages(
  url_hash text REFERENCES articles(url_hash) ON DELETE CASCADE,
  idx smallint,                        -- position in the body
  text text NOT NULL,
  embedding halfvec(768),
  embedding_model text,
  PRIMARY KEY (url_hash, idx))
  idx ix_article_passages_embedding_hnsw USING hnsw (embedding halfvec_cosine_ops) WITH (m=16, ef_construction=64)
  idx ix_article_passages_text_fts USING gin (to_tsvector('english', text))
  idx ix_article_passages_unembedded (url_hash) WHERE embedding IS NULL   -- the embedder queue
```

Roles: new `extractor_rw` NOLOGIN (like the others): SELECT on `articles`, SELECT/INSERT/UPDATE on `article_bodies`, SELECT/INSERT on `article_passages`. `embedder_rw`: SELECT and `UPDATE (embedding, embedding_model)` on `article_passages`. `api_rw`: SELECT on both. `sink_rw` needs nothing: its `DELETE` on `articles` cascades with the owner's rights. As today (found 2026-11-02 **[verified]**) the compose stack connects every service as the superuser, so the grants document intent and are enforced only if a service is switched to its role. Models `ArticleBody`, `ArticlePassage` in `newsdock_db.models` (`HALFVEC(768)` from `pgvector.sqlalchemy`); the autogenerate no-op test must stay green. The migration number follows the latest on the base branch (0011 today).

## 2. Statuses

| Status | Meaning | Final? |
|---|---|---|
| `pending` | queued or waiting for a retry (`next_attempt_at`), including after a 429, 5xx, timeout or unreachable robots.txt | no |
| `ok` | text stored (and passages) | yes |
| `blocked_robots` | robots.txt disallows us, or Crawl-delay above the cap, or robots unreachable for the whole attempt window | yes (robots are re-read per run, a later article of the site is tried again) |
| `blocked_address` | scheme, port, or any resolved address not allowed, at the first hop or in a redirect | yes |
| `http_error` | 4xx except 429 (incl. 403, 404, 451) or a 3xx without a usable `Location`, `http_status` set | yes |
| `not_html` | content type is not `text/html` / `application/xhtml+xml` | yes |
| `too_large` | body exceeded `max_bytes` | yes |
| `no_text` | extraction returned nothing or fewer than `min_chars` | yes |
| `failed` | 5xx, timeout or connection error after `max_attempts` | yes |

## 3. The extractor loop (`apps/extractor/src/newsdock_extractor/`)

Layers as every app: `domain/` pure (`passages.py`, `extract.py`, `schedule.py`, `status.py`), `adapters/` I/O (`db.py`, `fetch.py`, `robots.py`, `resolve.py`, `healthcheck.py`), `config.py`, `__main__.py` wires only.

```
every pass:
  discover()                     # insert pending rows for articles with seq > max(article_bodies.seq)
                                 # first run (table empty): only articles ingested in the last backfill_hours
  rows = next_batch(window)      # WHERE status='pending' AND next_attempt_at <= now()
                                 #   AND created_at >= now() - retention_days
                                 # ORDER BY seq DESC LIMIT batch_size
  chosen = scheduler.pick(rows)  # at most one row per host, only hosts whose delay elapsed
  run up to `concurrency` fetches at once (asyncio, httpx.AsyncClient), each:
      outcome = fetch_and_extract(url)           # §4, §5
      store(outcome)                             # one transaction: body row (+ passages when ok)
  heartbeat; sleep poll_interval_seconds only when nothing was due
```

- **Discovery.** (Implemented in T-08: `created_at` is copied from the article's `ingested_at`, so the retention window applies to the article and a late discovery cannot make an old article look new; the statement uses `RETURNING` because `rowcount` is -1 for it.) `INSERT INTO article_bodies (url_hash, seq) SELECT url_hash, seq FROM articles WHERE seq > :cursor [AND ingested_at >= :since on first run] ORDER BY seq LIMIT 1000 ON CONFLICT DO NOTHING`. The cursor is `max(article_bodies.seq)`. It relies on the same property as the platform's own cursor (one sink, commits in `seq` order). No back-fill of older articles.
- **Scheduler.** In memory: `next_allowed[host]`. A host is ready when `now >= next_allowed[host]`; after a fetch `next_allowed[host] = now + delay(host)`, where `delay = max(per_host_delay_seconds, Crawl-delay)`; a Crawl-delay above `max_crawl_delay_seconds` ends the article as `blocked_robots`. A restart forgets the map (first request to each site is immediate).
- **Retries.** Transient outcomes (**429**, 5xx, timeout, connection error; amended at T-01: 8 of 320 sampled URLs answered 429, which is a request to slow down, not a refusal) get `attempts += 1` and `next_attempt_at = now + retry_backoff_minutes[attempts - 1]` (default 5, 30; for a 429 with a `Retry-After`, the larger of the two, at most 60 minutes, and that site's delay is raised too), staying `pending`; at `max_attempts` (3) the status becomes `failed`. Everything else is final on the first try.
- **Fairness.** A site with thousands of pending articles gets one fetch per delay interval; others are not blocked. The batch (`batch_size`, default 200) is larger than `concurrency` so one slow site cannot starve the round.

## 4. Fetcher (`adapters/fetch.py`, `robots.py`, `resolve.py`)

1. **URL check.** Scheme `http` or `https`, host present, no userinfo, port empty or 80/443 only.
2. **Robots.** Per host, cached in memory (`robots_ttl_hours`, default 24): fetch `/robots.txt` through the same guarded client (own timeouts, 500 KB cap), parse with **Protego** (`pip: protego`, wildcards and `$` handled; Python's `urllib.robotparser` ignores them **[verified 2026-11-02]**: it wrongly allowed 3 of 6 test URLs). 401/403 → disallow all; other 4xx → allow all; 5xx, timeout or error → disallow for this attempt and cache the failure for `robots_failure_minutes` (RFC 9309 behaviour **[memory]**). `can_fetch(url, user_agent)` decides; `crawl_delay(user_agent)` feeds the scheduler. In the 40-site sample 9 sites disallowed us and 5 declared a Crawl-delay of 1–20 s **[verified]**.
3. **Resolve and pin.** `getaddrinfo` in a thread; every returned address must be `ipaddress.ip_address(...).is_global` (this refuses loopback, private, link-local, metadata `169.254.169.254`, CGNAT, multicast, and the compose service names, which resolve to private addresses). The first valid address is used for the connection.
4. **Request.** `httpx.AsyncClient(follow_redirects=False, trust_env=False, limits=httpx.Limits(max_keepalive_connections=0))`, a new client for each request (T-01: a pooled connection to an IP is reused without checking the claimed name again, so verification would be skipped); the URL is rewritten to the pinned IP with `Host` set and `extensions={"sni_hostname": host}` so TLS is verified against the site's name (`httpcore` 1.0.9 supports it **[verified]**; a spike test proves certificate checking still happens, T-02). Headers: `User-Agent` (descriptive, `extractor.user_agent`), `Accept: text/html,application/xhtml+xml`, `Accept-Language: en`. A cookie jar that rejects every cookie is used, so nothing is stored or sent.
5. **Redirects.** Up to `max_redirects` (3), each target re-run through steps 1, 3 (and robots for a new host); a loop or too many ends as `http_error`.
6. **Caps.** Connect 5 s, read 15 s, total 20 s per request; stream the body and stop at `max_bytes` (2,000,000) → `too_large`; require `text/html` or `application/xhtml+xml` → else `not_html`. (Spike values; all are settings and provisional.)

## 5. Extraction and passages (domain)

- `trafilatura.extract(html, url=url, include_comments=False, include_tables=False, include_links=False, include_images=False, favor_precision=False, output_format="txt")`, run in `asyncio.to_thread` (CPU-bound). `None` or fewer than `min_chars` (200, provisional) → `no_text`. Text longer than `text_cap_chars` (20,000) is cut at the last paragraph boundary below the cap.
- **Splitter** `split_passages(text, target=1000, hard_max=1200)`: split on blank lines; pack whole paragraphs until `target` would be exceeded; a paragraph longer than `hard_max` is split at sentence ends, then at spaces; no overlap (provisional; overlap is a tuning item for the evaluation backlog). Passages are numbered from 0; at most about 20 per body.
- Stored on `ok`: body text, and one `article_passages` row per passage (vector NULL), in the same transaction.

## 6. Embedder second pass (`apps/embedder`)

The same loop and `SkipList`/`Backoff`, a new `PassageRepo` beside `EmbedRepo`: `next_batch` = `SELECT url_hash, idx, text FROM article_passages WHERE embedding IS NULL ORDER BY url_hash... ` newest first (join to `article_bodies.seq` or order by `url_hash`; the plan picks by measuring), `store` = `UPDATE ... SET embedding, embedding_model WHERE (url_hash, idx) = ... AND embedding IS NULL`, `invalidate_stale` clears vectors of another model once at start. Text sent to Ollama is `embedding_document_prefix + passage text` (the title is not repeated: it has its own leg). Titles and passages alternate in the loop (titles first within a pass, so a flood of passages never starves them). New setting `embedder.passage_batch_size` (default 32).

## 7. API

- **Include.** `domain/include.py`: `INCLUDE_NAMES` gains `body`. `ArticleSummary.body: str|None = Field(None, exclude=True)`; `to_json(include)` writes it (null when none). The repo `_bodies_for(session, ids)` runs one query only when `body` is asked for (like events). Detail: `ArticleDetail.body`, `body_status` always (`none` when no row).
- **Scope.** `semantic_search(..., scope: str | None = None)`; `None` → `api.semantic_default_scope` (default `titles`); anything else than `titles`, `body`, `all` → `invalid_scope`. `SemanticService.search(..., scope)` builds legs: titles = existing `vector` + `keyword`; body adds `body_vector` and `body_keyword`; `all` has all four. `fuse()` is already generic over leg names, ties break by newest `published_at`. Embedding of the query is done once and shared by the title and passage vector legs.
- **Repo legs** (`SqlSemanticRepo`): `passage_vector_leg(vector, model, filters, limit)` = `article_passages JOIN articles` with `embedding <=> :vec`, filters via `apply_filters`, `hnsw.iterative_scan = relaxed_order`, top `semantic_passage_candidates` (150, provisional) passages, then the best passage per article in SQL/Python; `passage_keyword_leg` = `to_tsvector('english', text) @@ websearch_to_tsquery` ranked by `ts_rank`, best passage per article. Both return `Hit` plus the passage text.
- **Result.** `SemanticHit.passage: str|None` (`exclude=True`; written only when `scope` is `body` or `all`, so the default `titles` payload is byte-identical, AC-13). `matched_by` uses `vector`, `keyword`, `body_vector`, `body_keyword`. `degraded` keeps its meaning: hybrid lost every vector leg because the query could not be embedded. `vector` mode fails with `embedding_unavailable` for all scopes.
- **Settings** (`api`): `semantic_default_scope`, `semantic_passage_candidates`. OpenAPI: `body` documented on the detail and as an optional key on the feed twin; `scope` is an MCP argument only.

## 8. Settings (`infra/config/newsdock.yaml`, section `extractor`, all with code defaults, ADR-0013)

`poll_interval_seconds` 5, `batch_size` 200, `concurrency` 16, `backfill_hours` 6, `per_host_delay_seconds` 5, `max_crawl_delay_seconds` 30, `robots_ttl_hours` 24, `robots_failure_minutes` 60, `connect_timeout_seconds` 5, `read_timeout_seconds` 15, `total_timeout_seconds` 20, `max_bytes` 2000000, `max_redirects` 3, `min_chars` 200, `text_cap_chars` 20000, `passage_chars` 1000, `passage_max_chars` 1200, `max_attempts` 3, `retry_backoff_minutes` "5,30", `user_agent`, plus `db_backoff_seconds` 5 and `db_backoff_max_seconds` 60 (the wait after a failed pass, doubling up to the cap), `retention_days` (the extractor has its own copy because `sink.retention_days` lives in the sink section only; keep the two equal, the yaml row says so) and the heartbeat keys. All numbers are provisional (spec §6) except the 20,000-character cap and the 7 days, which are decisions.

## 9. Compose and tooling

- **Compose.** Service `extractor` (`profiles: [apps]`, restart `unless-stopped`, healthcheck on the heartbeat), `networks: [data]` (the owner's choice, ADR-0034), `depends_on` Postgres healthy and `migrate` completed, none on Kafka. No new network; the address guard (§4) is the only wall against SSRF.
- **A new app needs** (agent map, 2026-11-02): `apps/extractor/{pyproject.toml, Dockerfile, README.md, src/newsdock_extractor, tests}` with `domain/` and `adapters/`; `infra/scripts/check_layout.py` `PYTHON_APPS`; root `pyproject.toml` (mypy path, import-linter root packages, the independence contract, the DR-6 domain and forbidden contracts, the core/config/embedding forbidden lists); `uv.lock`; `Makefile` `PYTHON_APPS` and a test scene; `.github/workflows/ci.yml` path filter and matrix; `check_config.py` `SERVICES`; `test_ci_workflow.py`, `test_images.py`, `test_agent_isolation.py` (its exact service list), `test_check_layout.py`; `infra/scripts/check_docs.py` (its app list already omits the embedder); `CLAUDE.md` (app list, C-ids, fixed names, the scraping rule, the new tables and statuses); ADR-0034 for the new app folder.
- **Rule change.** `CLAUDE.md` GDELT rules say "Do not scrape article pages in the MVP" and the status line says M3 continues with body extraction; both are updated at implement time (D-4).

## 10. Failure table

| Failure | Effect | Handling |
|---|---|---|
| robots.txt unreachable | article waits and retries within `robots_failure_minutes`; not fetched blind | `pending` with `next_attempt_at` |
| DNS fails | transient | counts as `failed` attempt |
| Address private or loopback | refused | `blocked_address`, no packet sent |
| Redirect to a private address | refused at the hop | `blocked_address` |
| TLS certificate invalid | transient-looking error | `failed` after retries (never disabled verification) |
| 200 with a login or consent page | stub text | `no_text` below `min_chars`, otherwise stored (backlog) |
| Huge page | stopped while streaming | `too_large` |
| Postgres down | pass fails, nothing lost | loop backoff, rows stay pending |
| Ollama down | passages without vectors | embedder backoff, `degraded` in search |
| Two extractors by mistake | duplicate fetches, no duplicate rows | `ON CONFLICT`, status updated only from `pending` |

## 11. Security

Page content is untrusted: HTML is parsed only by `trafilatura`/`lxml` (no scripts run), only plain text is stored and served as JSON text, and any UI must escape it. No cookies or credentials are sent or kept; the worker holds no secrets beyond the database URL. The address guard is the single wall against SSRF (the extractor sits on the `data` network with Kafka and the workers, ADR-0034), so it has a test for every refused class: loopback, private, link-local, metadata, compose service names, `host.docker.internal`, IPv6 forms, non-http schemes, other ports, and redirects to each of them. A `crawl` network is a hardening option in the backlog. Text is served only through the authenticated API; the default stack is local only.

## 12a. Spike result (T-01, 2026-11-02) **[verified]**

Three parts, scripts kept out of the repo, no page content stored:

1. **Pinned-address TLS** works with `httpx` 0.28.1 / `httpcore` 1.0.9 and `sni_hostname`, with one pitfall: never reuse a connection across requests (see §4 step 4 and spec §3). `trustme` 1.2.1 (last release 2025-01-02, Python ≥ 3.9) builds the throwaway CA for the local TLS tests and is acceptable as a dev dependency.
2. **Article-weighted sample** (320 URLs, 231 sites): 69.7% `ok`, 14.4% `blocked_robots`, 13.1% `http_error` (403 22, 451 11, 429 8), 1.6% robots unreachable, 0.6% `no_text`, 0.6% `failed`; text median 2,957 characters; mean 4.7 passages per usable article; 33 KB median on the wire (156 KB decoded); fetch median 0.39 s; extraction median 17 ms. `min_chars` = 200 only removed 0.6%. One worker pass fetched 320 pages from 231 sites in 35 s, far above the 0.6–0.9 pages a second the feed needs.
3. **Passage storage** (100,000 synthetic passages of 1,000 characters, random vectors, throwaway Postgres): `halfvec(768)` table 4,940 B per passage in total (HNSW 2,048 B, full-text 261 B, key 32 B, the rest is the text and the vector), `vector(768)` 9,441 B (HNSW 4,096 B, since only 2 elements fit a page). HNSW build 77 s per 100,000 rows (`m=16`, `ef_construction=64`), full-text build 7 s, HNSW top-50 median 6 ms (p95 290 ms, cold), full-text top-50 median 0.9 ms. Parallel HNSW builds need more shared memory than a default Docker container has (64 MB); the migration builds the index on an empty table, so it is not affected, and a bulk rebuild must set `max_parallel_maintenance_workers = 0`.

Estimates that follow: 50–75 k articles a day × 70% usable × 4.7 passages is 164–247 k passages a day, 1.15–1.7 M in 7 days, **6–8.5 GB** for `article_passages` (11–16 GB with full vectors); embedding them at 67–70 passages a second takes about 0.7–1 hour a day; wire traffic is about 2–3 GB a day.

Amendments to the design made from these findings: no connection reuse (§4), 429 is transient (§2, §3, tests TC-8, TC-11, TC-12, AC-5 wording in the spec). Neither changes a decision (D-1…D-6, ADR-0034…0037).

## 12. Extension points (backlog)

A second fetcher (headless browser) behind the same `Fetched` result; PDF text; fetching copies in `article_sources`; an evaluation set and the `semantic_default_scope` flip; `halfvec` already chosen, smaller dimensions would need a new model.
