# Tests — body-extraction

Derived from the ACs in [spec.md](spec.md) §6. Levels: unit (no I/O), integration (Docker with a throwaway Postgres from `side_db`, or a local test web server), e2e, manual. Docker tests never share the dev stack's ports (`CLAUDE.md`).

## Test data

- **No real article HTML in the repo** (spec risk): fixtures are hand-made, news-shaped pages in `apps/extractor/tests/fixtures/` — `news_page.html` (navigation, ad blocks, cookie banner, a long main text of several paragraphs, a footer), `long_page.html` (main text over 40,000 characters), `stub_page.html` (a consent/paywall stub of about 150 characters), `non_article.html` (a link list), plus `robots_*.txt` samples (wildcard, `$`, Allow/Disallow, `Crawl-delay`, a group for our agent and a `*` group).
- **A local test web server** (`http.server` in a thread on `127.0.0.1`, started by a fixture) that serves the fixtures, answers chosen statuses (403, 404, 451, 500), delays, redirects (to another path, to `127.0.0.1:<other port>`, to a private address), a non-HTML body, an oversize body, a `Set-Cookie`, and records every request (path, headers, time). A local TLS variant uses a throwaway certificate authority created in the test (`trustme`, a dev dependency; T-01 confirms it).
- **Address policy for tests:** the fetcher takes an injected resolver and an `AddressPolicy`; the production policy refuses everything non-global, the test policy can allow loopback so the local server is reachable. No setting or environment variable can enable it in production.
- **Database tests** take the `side_db` pattern (own compose project, free port) and use `newsdock_db.testing.article(...)` and `make_vec` for articles and vectors, `FakeOllama` for embeddings.
- **Search fixtures:** synthetic passages with `make_vec(...)` directions, as the title-search tests do; paraphrase cases are built by vector direction, not by real language.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given the `robots_*.txt` samples, When `can_fetch` is asked, Then wildcard (`/*/amp/`), `$`, longer-Allow-wins and group selection follow Protego; 401/403 on robots.txt means disallow all, another 4xx allow all, 5xx or timeout disallow for now |
| TC-2 | AC-1 | integration | Given a site whose robots.txt disallows our agent for an article path, When the extractor processes that article, Then the page path is never requested (server log), the body row is `blocked_robots` with no text |
| TC-3 | AC-2 | unit | Given a fake clock, three pending articles on one host and one on another, and a per-host delay, When the scheduler picks, Then it returns at most one per host per round, the first host's second article only after the delay, and the other host is never held up |
| TC-4 | AC-2 | unit | Given a host declaring `Crawl-delay` 20 and another 60 (cap 30), When scheduled, Then the first waits max(delay, 20) and the second article ends `blocked_robots` without a request |
| TC-5 | AC-2 | integration | Given the local server, When the extractor fetches robots.txt and a page, Then both requests carry the descriptive `User-Agent` and `Accept` headers |
| TC-6 | AC-3 | unit | Given addresses 127.0.0.1, ::1, 10.0.0.5, 172.16.0.1, 192.168.1.1, 169.254.169.254, 100.64.0.1, fc00::1, ::ffff:127.0.0.1, a fake resolver mapping `postgres` and `localhost` to private addresses, URLs with userinfo, `file:`/`ftp:` schemes and port 8080, When checked, Then each is refused with `blocked_address` and a public address on 80/443 is accepted |
| TC-7 | AC-3 | integration | Given a page that redirects (a) to a private address and (b) to a refused scheme, When fetched, Then the target is never requested and the status is `blocked_address`; a redirect chain longer than the limit ends `http_error` |
| TC-8 | AC-3 | integration | Given a resolver that answers a public address first and a private one on the second lookup, When a page is fetched, Then the connection goes to the first (pinned) address and there is no second lookup; and with the local TLS server a certificate that does not match the site name fails verification while the matching one succeeds, also when an earlier request to the same address succeeded (no connection reuse across requests, T-01 finding) |
| TC-9 | AC-4 | unit | Given `news_page.html` and `long_page.html`, When extracted, Then the text holds the main paragraphs and none of the navigation, ad or banner text, and for the long page is at most 20,000 characters and ends at a paragraph boundary; status `ok` |
| TC-10 | AC-4, AC-5 | unit | Given `stub_page.html` and `non_article.html`, When extracted, Then the status is `no_text` (below `min_chars` or nothing extracted) and no passages are made |
| TC-11 | AC-5 | integration | Given the local server answering 403, 404, 429, 451, 500, a read timeout, `application/pdf`, a body over `max_bytes`, and an empty 200, When each is processed, Then the statuses are `http_error` (403, 404, 451, with `http_status`), retry-then-`failed` (429, 500, timeout), `not_html`, `too_large`, `no_text`, none with text |
| TC-12 | AC-5 | unit | Given the retry policy (max 3 attempts, delays 5 and 30 minutes), When a 5xx or a 429 repeats, Then `attempts` and `next_attempt_at` grow (a 429 honours `Retry-After` within the cap), the third failure is final `failed`, and any other 4xx is final at once |
| TC-13 | AC-6 | integration | Given an article with a body row, When the extractor runs again or the same article is delivered twice or two workers race, Then no request is made for it, one row exists, and the status only changes from `pending` |
| TC-14 | AC-7 | integration | Given pending rows of different ages and an empty body table with articles of the last hours and older, When the queue is read and discovery runs, Then rows come newest first, rows older than the retention window never, and on an empty table only the last `backfill_hours` are discovered; later discovery continues after `max(seq)` |
| TC-15 | AC-8 | integration | Given bodies and passages for articles older and newer than 7 days, When the sink's retention delete runs, Then the older articles' bodies and passages are gone and the newer ones stay |
| TC-16 | AC-9 | integration | Given articles with an `ok` body, a `pending` row, a `blocked_robots` row and no row, When `get_article` (MCP) and `GET /api/articles/{id}` are called, Then `body` is the text for `ok` and null otherwise, and `body_status` is `ok`, `pending`, `blocked_robots`, `none` |
| TC-17 | AC-10 | integration | Given the same articles, When any list or search tool and `GET /api/articles` are called with `include=body` and without, Then with it each article has `body` (null when none), without it (and with tone or events only) the keys equal the pre-change golden set; `include=body,events,tone` works and an unknown name is still `invalid_include` / 422 |
| TC-18 | AC-11 | unit | Given bodies of different shapes (short, many paragraphs, one huge paragraph, only whitespace), When split, Then passages are numbered from 0, none exceeds `passage_max_chars`, whole paragraphs are packed up to `passage_chars`, and the concatenation covers the text |
| TC-19 | AC-11 | integration | Given passages without vectors and `FakeOllama`, When the embedder's passage pass runs, Then every passage gets a vector of the configured model and dimension; passages of another model are cleared and re-embedded; a failing batch backs off like titles; a body yields passages exactly once |
| TC-20 | AC-12 | integration | Given embedded passages and a query whose vector matches a passage but whose words are absent, When `semantic_search` is called with `scope` `body` in `vector` and `hybrid` mode, with and without time, theme, domain and `min_negativity` filters, Then the article is returned with its best passage and a score, and each filter excludes what it should |
| TC-21 | AC-12, AC-13 | unit | Given a fake repo with legs for titles and passages, When the service runs each scope, Then the legs used, their fusion by rank, `matched_by` names, the passage of the best leg and the ordering follow the design; unknown scope raises `invalid_scope` |
| TC-22 | AC-13 | integration | Given one article matching only by title, one only by a passage, one without a body, When `scope` `all`, `titles` and no scope are called, Then `all` returns all three with `matched_by` and the passage where one matched; `titles` and no scope return exactly the previous payload (existing golden-key tests unchanged); setting `api.semantic_default_scope` to `all` changes the default |
| TC-23 | AC-14 | integration | Given the query embedder fails, When `scope` `body` or `all` is called, Then `vector` mode is `embedding_unavailable` and `hybrid` returns the keyword results with `degraded` true |
| TC-24 | AC-15 | e2e | Given a chain on a `side_db` Postgres (fake GDELT, `route()`, sink writers) and the extractor stopped or its fetcher failing, When slots keep arriving and an agent searches titles and reads articles, Then ingestion, title search and `get_article` behave as before; and the API package imports no fetcher and a socket guard shows it opens no outbound connection |
| TC-25 | AC-15 | e2e | (dev stack stopped) the compose stack starts with the `extractor` service healthy and the agent-isolation test's exact service list updated |
| TC-26 | AC-16 | manual | Checklist below |
| TC-27 | AC-6, AC-8 | unit+integration | Migration 0012 passes `test_migration_files.py`, autogenerate against the models is a no-op, grants exist for `extractor_rw`, `embedder_rw`, `api_rw`, status check constraint rejects unknown statuses, cascade from `articles` works |
| TC-28 | all | unit | `make config-python` green with the `extractor` section and the new `api` and `embedder` keys |
| TC-29 | tooling | unit | `check_layout.py`, import-linter contracts, CI workflow test and image test know the app `extractor`; `domain/` of the new app imports no I/O |
| TC-30 | AC-2, AC-3 | integration | Given a server that sets a cookie, When two pages are fetched, Then no `Cookie` header is sent on the second request |
| TC-31 | AC-9, AC-10 | unit | `test_openapi_contract.py`: the committed `openapi.json` equals `create_app().openapi()` and documents `body` and `body_status` |

## Manual checklist (AC-16, the owner's)

1. `make down`, `make build`, `make up`, `make migrate` (applies 0012); confirm the `extractor` service is healthy.
2. Wait for one or two slots to be ingested and the extractor to work for a while (a few minutes).
3. `select status, count(*) from article_bodies group by status;` and write the counts down; check a few `blocked_robots` and `http_error` rows look plausible.
4. Pick an `ok` article: `get_article` returns text; `select count(*) from article_passages where embedding is not null;` is growing.
5. Call `semantic_search` with `scope` `body` and `scope` `all` on a topic you know is in the news; record whether the returned passages are relevant.
6. Look at the extractor log for one site: requests are spaced and no request goes to a private address.

## Measurements (provisional targets, not pass/fail)

| ID | What | How |
|---|---|---|
| M-1 | Share of canonical articles that end `ok`, per status, article-weighted | `article_bodies` counts by status after a day (T-01: 69.7% on 320 article-weighted URLs, 65% on one URL per site) |
| M-2 | Fetch rate and backlog | pending count over time, fetches per hour |
| M-3 | Bandwidth per day | bytes read by the fetcher (logged) |
| M-4 | Passages per article and bytes per passage with its HNSW and full-text indexes | `count(*)`, `pg_total_relation_size('article_passages')` after 100 k synthetic passages (T-01) and after a day live |
| M-5 | Extraction CPU time per page | median and 95th percentile in the fetcher log |
| M-6 | Embedding backlog | `count(*) from article_passages where embedding is null` over time; hours to drain |
| M-7 | Retrieval smoke check | 10 hand-written questions on a day of real data: does `body` or `all` return a relevant passage in the top 5 more often than `titles`; recorded, not a pass/fail |

## AC coverage

AC-1 (TC-1, 2), AC-2 (TC-3, 4, 5, 30), AC-3 (TC-6, 7, 8, 30), AC-4 (TC-9, 10), AC-5 (TC-10, 11, 12), AC-6 (TC-13, 27), AC-7 (TC-14), AC-8 (TC-15, 27), AC-9 (TC-16, 31), AC-10 (TC-17, 31), AC-11 (TC-18, 19), AC-12 (TC-20, 21), AC-13 (TC-21, 22), AC-14 (TC-23), AC-15 (TC-24, 25), AC-16 (TC-26). TC-28 and TC-29 are cross-cutting guards.
