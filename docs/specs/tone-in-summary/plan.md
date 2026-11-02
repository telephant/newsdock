# tone-in-summary — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation

Run 2026-10-30 (see §6 for the commands).

| # | Check | Result |
|---|---|---|
| 1 | Every AC has at least one test; no test without an AC | pass (AC-1 … AC-15 ← TC-1 … TC-21) |
| 2 | Every AC maps to design components; every AC is implemented by a task | pass |
| 3 | Names consistent across spec, design, diagrams, tests, tasks (`include`, `min_negativity`, `invalid_include`, `invalid_filter`, `to_json`, `dump_page`, C-60…C-67) | pass |
| 4 | No doc treats a Proposed ADR as decided | pass (ADR-0030 is Accepted 2026-10-30) |
| 5 | Untagged claims, invented numbers, missing glossary terms | pass; the only numbers are measured values from the dev database, tagged in spec §3, and the 0–100 range, tagged **[memory]** |
| 6 | Nothing from `backlog.md` leaked into scope | pass (no UI, no sort, no index, no live-feed parameter) |
| 7 | Open questions and unchecked checklist items | none; design §8 is fully ticked |

Findings fixed while planning: spec AC-13 reworded for a non-number on an MCP tool (design 2026-10-30). Open risks carried into implementation: **R-1** the FastAPI `responses=` schema and the framework's validation error for a non-number are not yet run (de-risked by T-01); **R-2** the filter's latency is unmeasured (M-1).

## 1. Spike first

**T-01** runs the unverified claims on throwaway code before anything is built: (a) `response_model=None` with `responses={200: {"model": …}}` puts the optional tone keys in the OpenAPI schema and a returned `JSONResponse` is not re-validated; (b) `dict(summary)` includes `exclude=True` fields; (c) a FastMCP tool typed `float | None` rejects `"abc"` with a tool error; (d) `cast(literal(9.7), REAL)` makes a stored `real` 9.7 compare equal on the side Postgres. If (a) or (c) fails, ADR-0030 and the design are amended before T-02.

## 2. Tasks (walking skeleton order)

| Task | Title | Implements | Components | Depends on |
|---|---|---|---|---|
| T-01 | Spike: schema, validation, `dict()` and `real` cast | (de-risks AC-1, AC-13, AC-15, AC-9) | C-61, C-62, C-66 | — |
| T-02 | Tone rules and the test row helper | AC-2, AC-6, AC-13 | C-60 | T-01 |
| T-03 | Records: excluded fields, `to_json`, `dump_page`, detail fields | AC-1, AC-7, AC-8 | C-61 | T-02 |
| T-04 | Repo and service: `include`, `apply_filters(min_negativity)` | AC-9, AC-14 | C-62, C-64 | T-03 |
| T-05 | Semantic search: filter in both legs, hits carry tone | AC-10 | C-63 | T-04 |
| T-06 | Subscriptions: `min_negativity` in the saved filter and the stream | AC-12, AC-13 | C-65 | T-04 |
| T-07 | MCP tools: `include` and `min_negativity` | AC-1…AC-7, AC-10, AC-13 | C-66 | T-05, T-06 |
| T-08 | REST feed and detail | AC-1, AC-5, AC-6, AC-8, AC-11, AC-13 | C-66 | T-05, T-06 |
| T-09 | Contract, web and docs | AC-15 | C-67 | T-07, T-08 |

Milestones: after **T-04** an agent-free repo test proves the filter (AC-9, AC-14); after **T-07** an MCP client can read tone and filter (the digest agent's need); after **T-09** the contract, web types and docs agree and `make check` is green.

## 3. Effort (rough, one person with an assistant)

| Phase | Tasks | Estimate |
|---|---|---|
| Spike | T-01 | 0.5 h |
| Domain and data | T-02, T-03, T-04, T-05 | 3 h |
| Subscriptions | T-06 | 1 h |
| Surfaces | T-07, T-08 | 2.5 h |
| Contract, web, docs, checks | T-09 | 1.5 h |
| **Total** | | **about 8.5 h** |

## 4. Definition of done (every task)

- Tests are written first and seen to fail, then green.
- `make test APP=api` (and `make test APP=web` for T-09) is green; `make test-infra SCENE=api` runs the Docker tests that task adds, on the `side_db` fixture only.
- `make check-python` (ruff, mypy strict, import-linter, layout, config) is green after each task; `make check` at T-09.
- The docs a task touches are updated in the same edit (CLAUDE.md fixed names at T-09; status and plan marks per task).
- No secrets; SQL stays parameterized and inside `adapters/`; `domain/` gains no I/O import.
- The default payload test (TC-1, TC-2, TC-3) stays green in every later task: a failure there is a bug, never a test to edit.

## 5. Out of scope for this plan

UI display of tone, using tone in the whathappen agent, sort by negativity, an index on `tone_neg`, a filter on `list_new_articles` or `/api/live`, `include` on streams (all in [backlog.md](backlog.md)).

## 6. Validation commands run

```
for i in $(seq 1 15); do grep -q "AC-$i\b" tests.md || echo "no test AC-$i"; done
grep -o "TC-[0-9]*" tests.md | sort -u   # every TC appears in a task
grep -n "Proposed" ../../adr/0030-*.md   # none
uv run python infra/scripts/check_docs.py
```

## 7. Status

| Task | Status |
|---|---|
| T-01 | ✅ 2026-10-30 — spike: all four claims hold ([spike.md](spike.md)); one refinement, MCP `min_negativity` is declared strict (`"8"` and `true` were coerced); design-detail §7, T-07, TC-18 and AC-13 updated |
| T-02 | ✅ 2026-10-30 — `domain/tone.py` (`TONE_FIELDS`, `parse_include`, `check_min_negativity`, two error types), `test_tone.py` 33 passed, `article()` helper takes optional tone numbers; ruff, mypy strict, import-linter green |
| T-03 | ✅ 2026-10-30 — `ArticleSummary` tone fields (`exclude=True`), `to_json`, `dump_page`, `ArticleDetail` +3 fields, documentation models `ArticleSummaryTone` / `FeedPageTone`; `test_records_tone.py` 10 passed; API unit suite 410 passed, ruff, mypy green |
| T-04 | ✅ 2026-10-30 — repo `include` + `apply_filters(min_negativity)` with the `real` cast, service pass-through, detail fills all four numbers; `test_tone_repo.py` 11 passed (Docker, `side_db`), `test_service_tone.py` 5 passed; existing `FakeRepo`, `test_filters_repo` helper and the stream's `query` typing adjusted for the new keywords; mypy, ruff, import-linter green; API unit 390 passed, 49 Docker tests in the five touching modules passed |
| T-05 | ✅ 2026-10-30 — `SearchFilters.min_negativity`, both legs through `apply_filters`, `summaries(ids, include)`, `SemanticService.search(min_negativity, include)`; `test_semantic_tone_service.py` 4 passed, `test_semantic_tone.py` 5 Docker passed, the 26 semantic Docker tests pass; existing semantic fake takes `include`; ruff, mypy, import-linter green |
| T-06 | ✅ 2026-10-30 — `SubscriptionFilter.min_negativity` (number 0..100, no bool/str), numbers allowed in `SubscriptionRecord.filter`, `Mapping` on the store `create`, stream query carries the key; `test_subscription_tone.py` + route tests in `test_subscriptions_api.py`; `test_stream_tone.py` 2 Docker passed (only the 12.5 article is delivered, payload has no tone keys); two `as_query` assertions updated as planned; API unit 420 passed, 37 Docker stream/subscription/live tests passed; ruff, mypy, import-linter green |
| T-07 | ✅ 2026-10-30 — MCP `search_articles`, `semantic_search`, `list_new_articles` take `include`; the first two take a strict `min_negativity`; named tool errors `invalid_include` / `invalid_filter`; `test_tone_mcp_api.py` 21 passed (Docker, live app on `side_db`), existing MCP modules 16 passed; API unit 420 passed; ruff, mypy green |
| T-08 | ✅ 2026-10-30 — `GET /api/articles` takes `include` and `min_negativity`, returns a `JSONResponse` built by `dump_page`, documented with `responses={200: {"model": FeedPageTone}}`; 422 `invalid_include` / `invalid_filter`; detail returns all four numbers; `test_tone_rest_api.py` 22 passed (Docker, in-process client on `side_db`); 83 Docker tests across the seven touching modules passed; API unit 420 passed; ruff, mypy green |
| T-09 | ✅ 2026-10-30 — `openapi.json` and `types.ts` regenerated (regenerating again is byte-identical), `test_openapi_contract.py` 4 passed (drift test), web `features/feed/api.ts` aliases re-pointed at `ArticleSummaryTone` / `FeedPageTone` (found here), TC-21 added to `Subscriptions.test.tsx`; CLAUDE.md (status, tone arguments, push filter), README, roadmap updated; `make check` exit 0 (763 Python tests, 182 web tests, ruff, mypy strict, import-linter, layout, config, docs); the 62 new Docker tests pass together |
