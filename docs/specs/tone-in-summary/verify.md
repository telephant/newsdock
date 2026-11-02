# tone-in-summary — Verify

Verified 2026-10-30 on branch `agents-whathappen`, in the worktree `p2-delivery` (working copy, nothing committed). **Verdict: pass with follow-ups.** All 15 ACs hold with their named tests passing in this run; the follow-ups are a live check on a rebuilt dev stack and the first consumer of the new fields.

## What was run in this session

| Run | Result |
|---|---|
| `make check` (ruff, ruff format, mypy strict, import-linter, layout, config, Python tests, web lint/format/types/style/tests, docs check) | exit 0; **763 Python passed** (397 deselected: Docker/Ollama marks); **182 web passed**; mypy: no issues in 281 files; import-linter: 5 kept, 0 broken |
| New and touched unit modules | 111 passed (`test_tone`, `test_records_tone`, `test_service_tone`, `test_semantic_tone_service`, `test_subscription_tone`, `test_openapi_contract`, `test_subscriptions_api`, `test_subscriptions`) |
| **Whole API Docker suite** (`pytest apps/api/tests/integration -m docker`, 298 tests, every module on its own `side_db`; the dev stack was running and was not touched) | **298 passed in 4 min 45 s, 0 failed, 0 skipped** |
| Of which new for this feature | 62: `test_tone_repo` 11, `test_semantic_tone` 6, `test_stream_tone` 2, `test_tone_mcp_api` 21, `test_tone_rest_api` 22 |
| Regenerating `types.ts` from the committed `openapi.json` | byte-identical (same SHA-1 before and after) |

## Results per acceptance criterion

| AC | Tests | Result | Evidence |
|---|---|---|---|
| AC-1 default payload unchanged | TC-1, TC-2, TC-3 | pass | `test_records_tone` (dump and `to_json(())` equal the golden key set even with tone filled); `test_tone_mcp_api::test_default_responses_have_exactly_the_golden_keys` (`search_articles`, `list_new_articles`, `semantic_search` in both modes); `test_tone_rest_api::test_default_feed_has_exactly_the_golden_keys`; the stream test shows an event payload with no tone keys |
| AC-2 `include` on `search_articles` | TC-4, TC-5 | pass | `parse_include` cases; MCP: only `tone_neg` added, equal to the stored value, `null` for the row without tone |
| AC-3 `include` on `list_new_articles` | TC-6 | pass | same article ids and same `next_cursor` with and without `include`, limit 3 |
| AC-4 `include` on `semantic_search` | TC-7 | pass | `vector` and `hybrid`; hits keep `score` and `matched_by` and carry `tone_neg` |
| AC-5 `include` on the REST feed | TC-8 | pass | `include=tone,tone_neg` adds only those keys; paging (`next_before`) unchanged; blank and repeated pieces tolerated |
| AC-6 unknown include name | TC-4, TC-9 | pass | unit: `InvalidInclude`; MCP: `invalid_include` on all three tools (a bare string fails the tool's own validation); REST: 422 `invalid_include` for `tone_x`, `Tone`, `tone,word_count`, `title` |
| AC-7 missing tone value | TC-10 | pass | row E: requested keys are `null`, unrequested keys absent (MCP and REST) |
| AC-8 detail returns all four numbers | TC-11 | pass | repo `get`, REST `GET /api/articles/{id}` (row A: -4.0, 1.5, 9.5, 11.0; row E: all `null`) |
| AC-9 `min_negativity` on `search_articles` | TC-12 | pass | 8 returns A, C, D, F (D on the boundary, E without tone excluded); 9.7 returns C, F (the `real` cast); 0 and 100 are the edges |
| AC-10 one filter in both search legs | TC-13 | pass | vector leg, keyword leg and both service modes; vector results equal the embedded subset of `search_articles`; hybrid keeps filtering with the embedder down (`degraded: true`) |
| AC-11 `min_negativity` on the REST feed | TC-14 | pass | 8, 9.7, 0, 100 and combinations |
| AC-12 `min_negativity` in a subscription | TC-15, TC-16 | pass | parse and storage form (old string-only filters unchanged); live stream delivers only the 12.5 article and its payload has no tone keys; the number round-trips through the JSONB column |
| AC-13 invalid `min_negativity` | TC-17, TC-18 | pass | unit: -0.1, 100.1, NaN, inf, `true`, `"8"` rejected; MCP: `invalid_filter` for out-of-range, tool errors for `"abc"`, `"8"`, `true`; REST: 422 for -1, 101, 100.5, abc, true, empty, nan, inf; subscription POST: 422 for 101, -1, true, "8" and nothing stored |
| AC-14 filters combine with AND | TC-19 | pass | repo (`search` and `list_new` with theme, domain, text, time range) and MCP |
| AC-15 one contract | TC-20, TC-21 | pass | `test_openapi_contract` (committed `openapi.json` equals the generated document; the feed parameters, optional tone keys and detail fields are present); web: numeric filter shown as `min_negativity: 8`; `types.ts` regenerates byte-identically |

## Measurements (provisional targets, dev database, read-only)

| ID | What | Result |
|---|---|---|
| M-1 | `search_articles`-shaped query with `min_negativity` on the dev table (177 707 rows; 14 052 with `tone_neg ≥ 8`; 47 431 published in the last 24 h) | `min_negativity 8`, LIMIT 20: **0.74 ms** (index scan on `published_at`, 354 rows filtered); with a 24-hour range: **0.13 ms**; with theme `ARMEDCONFLICT`: **3.8 ms**; no tone filter: 0.02 ms. Extreme threshold 35 (3 matching rows): **130 ms**, a full walk of the `published_at` index (177 704 rows filtered). No `tone_neg` index is needed for normal thresholds; the extreme case is the one to watch as the window grows |
| M-2 | Payload of the 200 newest real rows (JSON built in SQL with the API's default keys; approximate, jsonb spacing) | default **197 792 bytes**; plus `tone_neg` **202 265 (+2.3 %)**; plus all four **215 883 (+9.1 %)** |

## Doc drift

None open. Checked by script: every name the design promises (`parse_include`, `check_min_negativity`, `InvalidInclude`, `InvalidNegativity`, `TONE_FIELDS`, `to_json`, `dump_page`, `ArticleSummaryTone`, `FeedPageTone`, `invalid_include`, `invalid_filter`, the strict `Negativity` argument, `responses=`, the `real` cast) exists in the code; ADR-0030 is Accepted; CLAUDE.md (status, tone arguments, push filter), README, roadmap, design-detail and the task files agree.

Changes made while building that differ from the approved docs, all recorded where they belong:

- MCP `min_negativity` is a strict number (T-01 spike: `"8"` and `true` were silently coerced). Recorded in `spike.md`, design-detail §7, T-07, TC-18, AC-13.
- The web wrapper `features/feed/api.ts` re-points its `ArticleSummary` / `FeedPage` aliases at the renamed schemas (found at T-09). Recorded in design-detail §8 and T-09.
- Float noise worry from the design checklist did not appear: a stored `real` 9.7 reads back as `9.7` (spike (d)).
- Two existing assertions, three test fakes and one helper signature were updated for the new keyword arguments, as the plan said they would be.

## Scope

Nothing implemented outside the spec. Not built, on purpose: UI display of tone, sorting, an index on `tone_neg`, a filter on `list_new_articles` or `/api/live`, `include` on streams, any change to `agents/whathappen`. No migration, setting or dependency was added.

## Verdict and follow-ups

**Pass with follow-ups.**

| ID | Priority | Follow-up |
|---|---|---|
| F-1 | P2 | The running dev API container was built before this change and was started from another worktree (`roadmap-ui-design`), so the new arguments are not live there and rebuilding from this worktree would mix the two. Only the `api` service serves MCP, so only its image matters (no migration). When this branch is merged and that stack is rebuilt (`make build APP=api`, then recreate just that service with `docker compose --env-file .env -f infra/compose.yaml --profile apps up -d --no-deps api`; `make up` does not start apps), call `search_articles(min_negativity=8, include=["tone_neg"])` once with a real key. MCP over real HTTP is already covered by `test_tone_mcp_api` (21 tests) |
| F-2 | P1 | Use the fields in the digest agent: a "worrying now" top block ranked by coverage and `tone_neg` (already first in [backlog.md](backlog.md)) |
| F-3 | P2 | Nothing is committed. Commit and open a PR when ready; the work is in the working copy of the `p2-delivery` worktree |
| F-4 | P3 | Watch M-1's extreme-threshold case (130 ms full walk) as the table grows; add a `tone_neg` index only if it matters |
| F-5 | P2 | Carried over, not caused by this feature: the Kafka modules and whole-stack Docker scripts that earlier verifies left open are still unrun (run them with the dev stack stopped) |
