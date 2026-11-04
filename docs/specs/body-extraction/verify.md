# Verify — body-extraction (M3d)

Run 2026-11-03 on branch `agents-whathappen` (worktree `p2-delivery`); the work was committed and merged later (PR #8, 2026-11-04). When section 1 was first run the dev stack was running on 5433, 29092, 8000 and 3000, so no module that needs those ports was run; they ran afterwards with the stack stopped (section 1b).

**Verdict: pass with follow-ups.** AC-1…AC-16 pass in this run (AC-15: TC-24 in process, and TC-25 on the real compose stack after the dev stack was stopped, see §1b). AC-16 was run live (section 1c). The measurements are first readings only (minutes, not a day), so they stay open as follow-ups (F-2). `stage` is `done`. Follow-ups F-2…F-5 (F-1 closed).

## 1. What was run

| Run | Result |
|---|---|
| `make check` (ruff, format, mypy strict, import-linter, layout, config, docs, web lint/format/typecheck/tests, non-Docker pytest) | exit 0; 1,145 Python tests passed (510 Docker/rules tests deselected), 182 web tests passed |
| Every module that uses its own throwaway Postgres (`side_db`) in one run: `apps/extractor/tests`, `apps/embedder/tests`, `apps/api/tests`, `packages/db/tests`, `infra/scripts/tests/{test_body_pipeline,test_migration_files,test_events_pipeline}.py`, with `-m "docker or not docker"` | **1,219 passed in 378 s**; the side containers were removed afterwards |
| **Not run** (they need the dev stack stopped): TC-25 (`test_agent_isolation.py`, the compose stack with the `extractor` service healthy), `test_stack.py`, the Kafka modules | open, F-1 |
| `docker compose --profile apps config --services` | lists `extractor` next to the other services |

### 1b. Run with the dev stack stopped (2026-11-03)

The owner asked me to stop the dev stack (containers stopped, not removed; volumes kept). Then: `make test-infra SCENE=kafka` 5 passed (includes `test_topics.py` with the five topics and the ingester file repo); `SCENE=stack` 9 passed; `SCENE=e2e` (TC-25) 11 passed; `SCENE=images` 18 passed; `SCENE=pipeline` 2 passed; `make check` exit 0. This run found and fixed three defects that were not in the feature:

- **Stale image:** the first `stack` run created 3 topics, not 5, because `make up` runs the `topics` job from the existing `newsdock-processor:dev` image, built before M3c. Rebuilding (`make build`) fixed it. A dev stack needs `make build` before `make up` after this milestone (already in `CLAUDE.md`).
- **Stale test expectations** in `test_stack.py`: the topic count (3, now 5) and the pinned migration head (`0010`, now derived from the migration files).
- **Guard bug** in `infra/scripts/dev_stack_guard.py`: it refused every test after the first in a module whose module-scoped fixture starts the stack, so `test_agent_isolation.py` could never pass since the guard was added. It now checks the ports once per module, before the first test starts a container; `test_dev_stack_guard.py` has a test that reproduces it.

### 1c. Live check on a real stack (2026-11-03)

With the dev stack stopped, the images rebuilt (`make build`), `make up`, then `docker compose --profile apps up -d --wait`: all services healthy, `extractor` included. Compose reused the existing project `newsdock` and its data volume, so migrations 0011 and 0012 were applied to the owner's existing dev database (301,508 articles). A new `.env` (ignored by version control, generated admin token) was created in this worktree because the worktree that owned the old one no longer exists; the old admin token is gone, agents made before keep their keys.

Checklist of `tests.md` (TC-26):

1. Stack healthy with the `extractor` service: yes.
2. The extractor started on the last 6 hours of articles (no back-fill).
3. `article_bodies` after about 15 minutes: `ok` 508, `blocked_robots` 83, `http_error` 46, `no_text` 5, `too_large` 1, `pending` 10,289. Of the 643 finished, 79% are `ok` (T-01 estimated 69.7%). Later reading at 08:25 (6,436 finished): `ok` 4,875 (75.8%), `blocked_robots` 1,013 (15.7%), `http_error` 478 (7.4%), `no_text` 66 (1.0%), `failed` 0; pending 6,990.
4. `get_article` of an `ok` article returned its text (2,897 characters) over MCP and REST; `include=body` worked on the feed; `article_passages` 2,359, all embedded (about 4.6 passages per `ok` body).
5. `semantic_search` with a query built from words of a body (not of its title): `scope=titles` did not return the article, `scope=body` returned it first with the matching passage (`matched_by` `body_vector` and `body_keyword`), `scope=all` returned it first with `vector`, `body_vector`, `body_keyword`; `titles` results carry no `passage` key.
6. Extractor log: every request goes to a public address (the pinned IP), `robots.txt` is read before the page, redirects are followed one hop at a time.

Throughput (M-2): 1,640 pages in 5 minutes, about 320 a minute, five times the arrival rate, so the queue drains (F-6 resolved).

Sizes after the first minutes (small tables overstate the index share): `article_passages` 5.9 MB for 768 passages (about 7.7 kB each), `article_bodies` 4.0 MB for 10.9 k rows.

## 2. Acceptance criteria

| AC | Test cases | Result | Evidence (this run) |
|---|---|---|---|
| AC-1 robots.txt respected | TC-1, TC-2 | pass | `apps/extractor/tests/unit/test_robots.py`, `integration/test_loop_db.py` (a `blocked_robots` row, the page never requested) |
| AC-2 one site at a time, spaced | TC-3, TC-4, TC-5, TC-30 | pass | `unit/test_schedule.py`, `integration/test_fetch.py` (no `Cookie` header on the second request), `test_loop_db.py` |
| AC-3 non-public addresses refused | TC-6, TC-7, TC-8 | pass | `unit/test_resolve.py`, `integration/test_fetch.py` (redirect hops re-checked), `blocked_address` stored |
| AC-4 text extracted and stored | TC-9, TC-10 | pass | `unit/test_extract.py`, `unit/test_passages.py`, `integration/test_loop_db.py` |
| AC-5 failures get a status and bounded retries | TC-10, TC-11, TC-12 | pass | `unit/test_retry.py`, `unit/test_status.py`, `integration/test_loop_db.py` |
| AC-6 one row per article, no refetch | TC-13, TC-27 | pass | `integration/test_repo.py`, `packages/db/tests/integration/test_schema.py` |
| AC-7 newest first, window, discovery | TC-14 | pass | `unit/test_picking.py`, `integration/test_repo.py` |
| AC-8 retention cascades | TC-15, TC-27 | pass | `test_schema.py`, `test_repo.py` (body and passages deleted with the article) |
| AC-9 text of one article | TC-16, TC-31 | pass | `apps/api/tests/integration/test_body_api.py` (REST detail, MCP `get_article`; `ok`, `pending`, `blocked_robots`, `none`), `test_openapi_contract.py` |
| AC-10 opt-in text in lists | TC-17, TC-31 | pass | `test_body_api.py` (feed, `search_articles`, `list_new_articles`, `semantic_search`; golden keys without it; unknown name still 422 / `invalid_include`) |
| AC-11 passages are embedded | TC-18, TC-19 | pass | `apps/extractor/tests/unit/test_passages.py`, `apps/embedder/tests/unit/test_passages.py`, `integration/test_embedder_db.py` (once only, model change re-embeds, outage recovers) |
| AC-12 search over the text | TC-20, TC-21 | pass | `apps/api/tests/integration/test_semantic_body.py`, `unit/test_semantic_scope.py` (`vector` and `hybrid`, time, theme, domain and `min_negativity` filters) |
| AC-13 titles and text fused | TC-21, TC-22 | pass | `test_semantic_body.py` (title-only, text-only, body-less; `titles` payload keeps its keys; the default-scope setting) |
| AC-14 degrades like titles | TC-23 | pass | `test_semantic_body.py` (`vector` raises, `hybrid` is `degraded` with the keyword legs, scopes `body` and `all`) |
| AC-15 platform unaffected | TC-24, TC-25 | pass | `infra/scripts/tests/test_body_pipeline.py`: extractor stopped, then failing on every fetch; ingestion, sink replay, title search and `get_article` as before; the API read path opens no socket; no fetcher or parser imported by `apps/api/src`. TC-25: `test_agent_isolation.py` 11 passed, all ten services healthy including `extractor` |
| AC-16 one live slot | TC-26 | pass (manual, run by the agent with the owner's go-ahead, 2026-11-03) | live stack (section 1c): `article_bodies` by status, `get_article` text, `scope=body`/`all` passages, extractor log with public addresses only |

TC-27…TC-29 (migration, config, tooling lists) pass inside `make check` and the Docker run.

## 3. Measurements

None of M-1…M-7 can be read without the extractor running for a day on the live stack, so they are open. Closest evidence so far is from the T-01 spike (2026-11-02): 69.7% usable on 320 article-weighted URLs, 6–8.5 GB estimated for 7 days of `halfvec` passages (both still to be confirmed live, plan R-2).

## 4. Findings

| ID | Finding | Severity | Decision |
|---|---|---|---|
| F-1 | TC-25 and the whole-stack and Kafka modules had not run because the dev stack held their ports. | medium | **closed 2026-11-03**: dev stack stopped, `kafka` 5 passed, `stack` 9 passed, `e2e` 11 passed, `images` 18 passed, `pipeline` 2 passed (§1b) |
| F-2 | M-1…M-7 need a day of live running; only first readings exist (section 1c). Recall of text search is unmeasured (the evaluation set is a backlog item). | medium | read them after a day on the live stack |
| F-6 | **Throughput (first reading was misleading).** Fifteen minutes after start only 643 pages were done against 10,289 pending, which looked like falling behind. Two later readings show the opposite: 4,796 done at 08:20 and 6,436 at 08:25 (about 320 pages a minute, about 19,000 an hour) against an arrival of about 67 articles a minute (about 1,000 canonical articles per 15-minute slot); the pending queue fell from 10,289 to 6,990 even while two new slots arrived. The early number was start-up (robots.txt for every new site, a cold queue of one day of old articles). | low | resolved by measurement (M-2); recheck after a day, because the first-hour backlog and the per-site spacing may bind harder on a busy day |
| F-3 | AC-15 "the API makes no outbound request" is shown for the repo read path (a socket spy) and for the imports of `apps/api/src`, not for a running MCP server under traffic. The query embedder legitimately calls Ollama. | low | accepted; the TC-25 stack run adds the whole-service view |
| F-4 | The extractor shares the `data` network with Kafka and Postgres (ADR-0034, the owner's choice); the address guard is the only wall against SSRF, and compose connects as the database superuser, so the `extractor_rw` grants document intent only. | low | accepted in ADR-0034; the `crawl` network stays in the backlog |
| F-5 | `test_head_is_0010` had pinned the migration head and failed since 0011; it now compares against the Alembic script head. | low | fixed in this milestone |

## 5. Doc drift and scope

`CLAUDE.md` (status, app list, C-80…C-87, tables, the scraping rule, fixed names), `docs/roadmap.md` and the extractor README were updated at T-12. Names checked identical across code, docs and tests by grep: statuses (`pending`, `ok`, `blocked_robots`, `blocked_address`, `http_error`, `not_html`, `too_large`, `no_text`, `failed`), scopes (`titles`, `body`, `all`), leg names (`vector`, `keyword`, `body_vector`, `body_keyword`), `invalid_scope`, `passage`, `include=body`, settings `semantic_default_scope` / `semantic_passage_candidates` / `passage_batch_size`, tables `article_bodies` / `article_passages`, migration 0012. ADR-0034…0037 were not re-read line by line in this run. `docs/README.md` still says "ADR-0001 to ADR-0010" (stale before this milestone, not touched). The regenerated `openapi.json` and `types.ts` also carry the earlier M3c fields, because both are generated from the one app.

Scope: nothing from `backlog.md` was implemented (no evaluation set, `scope=all` is not the default, no copy fetching, no digest change, no `crawl` network).

## 6. Next

1. The owner stops the dev stack and runs F-1, then the live checklist (F-2) for both M3c (AC-14 of `events-mentions`) and M3d (AC-16).
2. Repeat `/spec-verify events-mentions` and `/spec-verify body-extraction` to close both.
3. Candidates after that, from `backlog.md`: the text-search evaluation set (P2), then `scope=all` as the default.
