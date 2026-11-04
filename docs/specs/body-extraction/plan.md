# Plan — body-extraction

Spec [spec.md](spec.md) · design [design.md](design.md) · tests [tests.md](tests.md). Implement one task at a time with `/spec-implement body-extraction T-NN`, tests first.

## Plan validation

Run 2026-11-02 with grep over the spec folder.

| # | Check | Result |
|---|---|---|
| 1 | Every AC (1…16) has at least one test case in `tests.md`; all 31 TCs exist and none is cited by a task without being defined; every TC is used by a task | pass |
| 2 | Every AC appears in `design.md` and in at least one task | pass |
| 3 | Names consistent across spec, design, diagrams, tests, tasks: tables `article_bodies`, `article_passages`; statuses `pending, ok, blocked_robots, blocked_address, http_error, not_html, too_large, no_text, failed` plus `none` in the API; `include=body`, `body`, `body_status`, `scope` (`titles`, `body`, `all`), `invalid_scope`, `passage`, leg names `vector`, `keyword`, `body_vector`, `body_keyword`; settings `semantic_default_scope`, `semantic_passage_candidates`, `passage_batch_size`; app `extractor`, network `data` | pass |
| 4 | No doc treats a Proposed ADR as decided: ADR-0034 (the owner chose option b), 0035, 0036, 0037 are Accepted 2026-11-02 | pass |
| 5 | Untagged claims, invented numbers, glossary | fixed: glossary gained Crawl-delay, Protego, pinned address and discovery pass; the 10-day effort is tagged **[assumption]**; the numbers in tests.md are provisional or labelled as such |
| 6 | Backlog items leaked into scope | none (no re-fetch, copies, PDF, JavaScript, paywall detection, UI, digest change, evaluation set, default flip or `crawl` network) |
| 7 | Open questions and unchecked checklist items | none: design checklist all ticked, D-1…D-6 decided |

Risks carried into implementation (not blockers):

- R-1 (closed 2026-11-02) The pinned-IP request verifies the TLS certificate (T-01), with one rule added: never reuse a connection across requests.
- R-2 (updated 2026-11-02) T-01 measured 69.7% usable (320 URLs) and 6–8.5 GB for 7 days of passages with `halfvec`; both are still read live (M-1, M-4).
- R-3 (medium) The extractor shares the `data` network with Kafka (the owner's choice); the address guard needs a test for every refused class. A `crawl` network is in the backlog.
- R-4 (low) Legal and terms questions about storing and serving page text are the owner's (spec risk); the data stays private.
- R-5 (low) Docker modules that need the dev stack stopped (`TC-25`, the compose service) are written and may stay unrun.
- R-6 (low) Adding an app touches many lists (layout check, import-linter, CI, isolation test); T-03 does them in one task so a miss fails `make check`.

Go: next step `/spec-implement body-extraction T-01`.

## Spike first

**T-01** de-risks the three biggest unverified claims before any production code: (1) that a request pinned to a validated IP address still verifies the site's TLS certificate with our `httpx`/`httpcore` versions (the whole SSRF design in ADR-0035 depends on it); (2) what share of canonical articles really yields text when weighted by article, not by site (the 65% came from one URL per site); (3) the real size of `halfvec(768)` passages with the HNSW and full-text indexes (the spec's storage risk). If a claim fails, the design changes before the app exists.

## Tasks (dependency order; milestone markers after T-08, T-09, T-10, T-11)

| Task | Title | AC | Depends on |
|---|---|---|---|
| T-01 ✅ 2026-11-02 | Spike: pinned-IP TLS, article-weighted fetch sample, `halfvec` size | prerequisite | none |
| T-02 ✅ 2026-11-02 | Migration 0012, models, grants, cascade | AC-6, AC-8 (schema) | T-01 |
| T-03 ✅ 2026-11-02 | App `extractor`: scaffold and every tooling list | tooling (TC-29, TC-28) | T-01 |
| T-04 ✅ 2026-11-02 | Domain: extraction, text cap, passage splitter | AC-4, AC-11 (splitter) | T-03 |
| T-05 ✅ 2026-11-02 | Domain: scheduler, retry policy, queue picking rules | AC-2, AC-5 (policy), AC-7 (picking) | T-03 |
| T-06 ✅ 2026-11-02 | Adapters: robots (Protego) and the address guard | AC-1, AC-3 | T-03 |
| T-07 ✅ 2026-11-02 | Adapter: pinned-IP fetcher (redirects, caps, no cookies) | AC-2, AC-3, AC-5 | T-04, T-06 |
| T-08 ✅ 2026-11-02 | Adapter: database repo, discovery, the extractor loop | AC-1, AC-6, AC-7, AC-8 | T-02, T-05, T-07 |
| T-09 ✅ 2026-11-03 | Embedder second pass for passages | AC-11 | T-02, T-04 |
| T-10 ✅ 2026-11-03 | API: `body` on the detail, `include=body`, OpenAPI | AC-9, AC-10 | T-02 |
| T-11 ✅ 2026-11-03 | API: `semantic_search` scopes `titles` / `body` / `all` | AC-12, AC-13, AC-14 | T-02, T-09 |
| T-12 ✅ 2026-11-03 | Compose service, independence e2e, `CLAUDE.md` and docs, live check | AC-15, AC-16 | T-08, T-09, T-10, T-11 |

**Milestones:** after T-08 the extractor stores bodies and passages from a local test web (AC-1…AC-8); after T-09 passages carry vectors (AC-11); after T-10 agents read the text (AC-9, AC-10); after T-11 they can search it (AC-12…AC-14); after T-12 independence (AC-15) is proven and AC-16 is the owner's live check.

T-04, T-05 and T-06 are independent of each other; T-10 can run in parallel with T-08 and T-09 once T-02 is done. The table is sequential for clarity.

## Effort (rough)

Spike 1 d · migration and scaffold 1.5 d · domain and adapters 3 d · repo and loop 1 d · embedder pass 0.5 d · API 2 d · compose, e2e, docs 1 d. About 10 days of focused work **[assumption]**.

## Definition of Done (every task)

- The tests listed in the task are written first and green; related existing tests stay green.
- `make check` green for the touched apps (`make test APP=<app>`), `make config-python` after config changes, `make check-web` after OpenAPI changes.
- Docker tests only on throwaway databases (`side_db`) while the dev stack runs; modules that need fixed ports only with `make down` (and say so when not run).
- Docs updated in the same edit where a fact repeats (`CLAUDE.md` fixed names, tables, statuses, the scraping rule at T-12; ADRs); `status.yaml` ACs updated.
- No secrets; SQL parameterised; no real article HTML committed; no request to a real site from any automated test.

## Out of scope (stays in `backlog.md`)

Re-fetching, copies in `article_sources`, PDFs, JavaScript rendering, paywall detection, web UI, the digest agent reading bodies, a retrieval evaluation set, making `scope=all` the default, a `crawl` network.
