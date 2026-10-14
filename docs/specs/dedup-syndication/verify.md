# dedup-syndication — Verification

Verified 2026-10-09 by running everything in this session. **Verdict: pass with follow-ups.** One real defect was found on live data (generic titles merged different pages) and fixed inside this milestone at the user's request (D-6, AC-13, ADR-0012 amendment); all results below are from the final code.

## Runs

| Run | Result |
|---|---|
| `make check` (ruff, format, mypy strict over 149 files, import-linter 4 contracts, layout, config check, 279 Python tests, web lint/format/typecheck/13 tests, docs check) | pass |
| `make test-infra` (every Docker scene against real Kafka/Postgres, incl. the new AC-13 test) | 56 passed, 227 s |
| Live stack on real GDELT data (3 slots, 4,110 copies), headless-Chrome screenshots, SQL checks | done, before and after the fix |

Flake found and fixed on the way: the heartbeat-stale test (`test_agent_isolation.py`, from the externalize-config work) raced with the worker rewriting `/tmp/healthy`; it now checks a separate stale file (3 consecutive green runs).

## Acceptance criteria

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 key normalization | TC-1 | pass | `packages/core/tests/unit/test_stories.py` (22 tests) |
| AC-2 canonical + sources | TC-2, TC-14 | pass | sink integration on Postgres; in-batch cache unit test |
| AC-3 cross-slot copy | TC-3 | pass | sink integration |
| AC-4 same-URL idempotency | TC-4 | pass | sink integration; live: `url-duplicates` counted, no new rows |
| AC-5 window guard | TC-5 | pass | sink integration (72 h apart → 2 canonicals); live max spread inside a story 9.3 h |
| AC-6 detail exposes sources | TC-6 | pass | api integration; live detail page lists 19 sources |
| AC-7 feed/search return stories once | TC-7 | pass | api integration with grouped, plain and NULL-key rows |
| AC-8 late copies do not re-emit | TC-8 | pass | api integration (cursor past a story) |
| AC-9 one analysis per story | TC-9 | pass | `infra/scripts/tests/test_story_agent.py` against the real API |
| AC-10 UI grouping (manual) | TC-10, TC-11 | manual-ok | live feed screenshot: `· 2 sites` only on stories with > 1 source (3 of 20 rows), none on single-source rows; detail screenshot of "Aerosmith Are Back…" shows "Seen on 19 sites" with all 19 links; unit tests for badge and escaping green |
| AC-11 retention cascades sources | TC-12 | pass | sink integration |
| AC-12 dedup ratio observable | TC-13 | pass | live sink log: `dedup: 141 canonicals, 59 grouped copies, 0 url-duplicates, 0 dlq` per batch |
| AC-13 look-alike pages don't group (new, D-6) | TC-15, TC-16 | pass | core `can_join`/`page_signature` tests on real URLs; writer unit tests; Postgres integration; live replay (below) |

## Measurements (provisional targets, not pass/fail)

Live GDELT slots 2026-10-08 13:00, 13:30, 14:00 UTC through the real pipeline.

| What | Target | Before the fix | After the fix |
|---|---|---|---|
| Stored-article reduction (copies → stories) | ≈ 14 % | 3,190 stories / 4,110 copies = **22.4 %** | 3,223 / 4,110 = **21.6 %** (higher than the guess because copies also group across slots; the 14 % was per slot) |
| Agent scoring calls (ECON_ prefilter, derived from the store) | ≈ duplicate rate | 721 vs 978 = 26.3 % fewer | 728 vs 979 = **25.6 % fewer** |
| False merges, hand-checked | ≈ 0 | **6 groups / 17 copies** of 261 multi-source groups (0.4 % of copies): site-name titles ("The Miami Student", "China Daily Website…"), a paywall banner, "Company Announcement" boilerplate | **0** of the six; all remaining same-domain groups reviewed (iHeart stations sharing a slug, one Daily Gazette article id, http/https variants of one page) |
| Max `published_at` spread inside a story (window 48 h) | < 48 h | 9.3 h | 9.3 h |
| Same-domain-only multi-source stories | n/a | 38 | 18 (the 20 dropped were 6 false merges plus URL variants such as rttnews and israelnationalnews ids, which stay separate as before M2a) |

The agent number is derived from the stored themes, not from a live LLM run; AC-9 itself is covered by the automated test. A real `llama3.2:3b` run was not done.

## Doc drift

| Finding | State |
|---|---|
| Design / ADR-0012 said grouping is title + window only | amended (ADR-0012 amendment 2026-10-09, design.md "Look-alike guard", design-detail pseudo-code, spec D-6 / AC-13 / glossary, tests.md TC-15/16, CLAUDE.md story line) |
| Schema (`articles.story_key`, `article_sources` columns, index) vs design §3 | matches |
| API fields `source_count`, `sources[]`, config `NEWSDOCK_STORY_WINDOW_HOURS` vs design | matches |
| Scope: fuzzy/embedding/backfill/canonical-quality/merge-repair in code | none found |

## Observations (not defects)

- The feed/detail wording "Seen on 19 sites" counts copies (URLs), not distinct sites: all 19 are iHeart radio stations on one registrable domain. Spec AC-10 says "seen on N sites"; kept as is.
- `story_key` is no longer unique across `articles` (24 keys had split stories in the live sample); nothing in the code assumes uniqueness.

## Follow-ups (accepted, moved to backlog.md)

1. **URL variants with different ids** (rttnews `story.aspx?Id=` vs `/<id>/slug.aspx`, israelnationalnews `/news/<id>` vs `/flashes/<id>`) no longer group; harmless duplicates, same as before M2a. Smarter same-page detection can wait for fuzzy matching (M3).
2. **Generic titles across *different* domains** are not guarded (none seen in the sample).
3. **"N sites" wording** vs distinct-domain count (P3).
4. Agent-call reduction measured from the store, not from a live LLM run (P3).
