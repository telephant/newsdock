# tone-in-summary — Tests

Derived from the ACs in [spec.md](spec.md) §6 and the design in [design.md](design.md). Every AC has at least one test and every test names its AC.

## 1. Test data and where it lives

- **Rows:** hand-made articles built with `newsdock_db.testing.article(...)`, which T-02 extends with optional `tone`, `tone_pos`, `tone_neg`, `tone_polarity` keyword arguments (default `None`, so no existing test changes). A shared set is defined once per test module:

  | key | tone | tone_neg | notes |
  |---|---|---|---|
  | A | −4.0 | 9.5 | has a vector, theme `ECON_RATES`, `a.com` |
  | B | 2.0 | 3.0 | has a vector, theme `ENV_FIRE` |
  | C | −12.0 | 12.5 | no vector, theme `ECON_RATES`, `b.com` |
  | D | −8.0 | 8.0 | exactly on the boundary for `min_negativity` 8 |
  | E | NULL | NULL | a row with no tone (AC-7, AC-9) |
  | F | −9.7 | 9.7 | stored as `real`; proves the `real` cast on the boundary (design tricky part 5) |

- **Real-data check (not a fixture):** the shape of the values (range −40 to 31.5, 15 NULL rows of 175 061) was read from the dev database during `/spec-init`; tests use the hand-made rows above, never the dev database.
- **Database:** Docker tests use the `side_db` fixture (own compose project, free port) and are marked `docker`. They never use the dev stack's ports (CLAUDE.md workflow rule). Run them with `make test-infra SCENE=api`; unit tests run with `make test APP=api`.
- **Live app:** MCP and REST tests reuse the pattern of `apps/api/tests/integration/test_semantic_mcp_api.py` (a uvicorn app on a side Postgres, an MCP client with an agent key, a fake query embedder that can be switched off); new tests go in `apps/api/tests/integration/test_tone_api.py` and `test_tone_repo.py`.
- **Golden key set (AC-1):** the exact keys of an article in each default response, copied from a real response before the change and stored in the test as a constant.

## 2. Test cases

Level: unit = no Docker; integration = `docker` marker (side Postgres, live app).

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | **Given** an `ArticleSummary` whose four tone fields are filled **When** it is dumped with `model_dump(mode="json")` and with `to_json(())` **Then** both equal the golden key set and contain no tone key |
| TC-2 | AC-1 | integration | **Given** rows A–F **When** `search_articles`, `list_new_articles` and `semantic_search` (both modes) are called through MCP without `include` **Then** every article has exactly the golden keys (plus `score`/`matched_by` for semantic hits) |
| TC-3 | AC-1 | integration | **Given** rows A–F and a session **When** `GET /api/articles` is called without `include` **Then** every article has exactly the golden keys and `next_before` is unchanged |
| TC-4 | AC-2, AC-3 | unit | **Given** `parse_include` **When** called with `None`, `[]`, `"tone,tone_neg"`, `["tone","tone","tone_neg"]` **Then** it returns `()`, `()`, `("tone","tone_neg")`, `("tone","tone_neg")`; and `to_json(("tone_neg",))` adds only `tone_neg` |
| TC-5 | AC-2 | integration | **Given** rows A–F **When** `search_articles(include=["tone_neg"])` is called **Then** each article has `tone_neg` equal to its stored value and none of `tone`, `tone_pos`, `tone_polarity` |
| TC-6 | AC-3 | integration | **Given** rows A–F **When** `list_new_articles(include=["tone","tone_neg"], limit=3)` is called and again without `include` **Then** the first carries both keys, and the `next_cursor` and article ids equal those of the second |
| TC-7 | AC-4 | integration | **Given** embedded rows A and B **When** `semantic_search` runs in `vector` and `hybrid` mode with `include=["tone_neg"]` **Then** each hit has `tone_neg`, `score` and `matched_by` |
| TC-8 | AC-5 | integration | **Given** rows A–F and a session **When** `GET /api/articles?include=tone,tone_neg` is called **Then** each article carries `tone` and `tone_neg` and no other tone key |
| TC-9 | AC-6 | unit + integration | **Given** `include` with an unknown name (`"tone_x"`) or an empty name **When** `parse_include` runs (unit), `search_articles`, `semantic_search`, `list_new_articles` are called, and `GET /api/articles?include=tone_x` is called **Then** `InvalidInclude` is raised, MCP answers a tool error starting `invalid_include`, REST answers 422 `invalid_include`, and no articles are returned |
| TC-10 | AC-7 | unit + integration | **Given** row E (NULL tone) **When** a list asks for `include=["tone","tone_neg"]`, and when it asks for nothing **Then** the first has both keys with `null` and the second has neither key (MCP and REST) |
| TC-11 | AC-8 | integration | **Given** row A with all four numbers stored **When** `get_article` and `GET /api/articles/{id}` are called **Then** both return `tone`, `tone_pos`, `tone_neg`, `tone_polarity` with the stored values |
| TC-12 | AC-9 | integration | **Given** rows A–F **When** `SqlArticleRepo.search(min_negativity=8)` and `search(min_negativity=9.7)` run **Then** the first returns A, C, D, F (D included, boundary inclusive) and not B or E; the second returns C and F only (F's stored `real` 9.7 equals the cast parameter) |
| TC-13 | AC-10 | integration | **Given** embedded rows with mixed `tone_neg` **When** the vector leg, the keyword leg and `SemanticService.search` in both modes run with `min_negativity=8` **Then** no hit has `tone_neg` below 8 in either leg and the set equals the embedded rows `search_articles` returns for the same filter |
| TC-14 | AC-11 | integration | **Given** rows A–F and a session **When** `GET /api/articles?min_negativity=8` is called **Then** only articles with `tone_neg` ≥ 8 are returned |
| TC-15 | AC-12 | unit | **Given** `parse_filter` **When** it receives `{"min_negativity": 8}`, `{"min_negativity": 8.5, "theme": "ECON_*"}` and `{}` **Then** `as_json()` stores the number only when given, `as_query()` carries `min_negativity`, and a filter saved before the change (strings only) still parses and serializes identically |
| TC-16 | AC-12 | integration | **Given** a subscription `{"min_negativity": 8}` and a stream **When** articles with `tone_neg` 3.0 and 12.5 are inserted **Then** only the 12.5 article is delivered, and the event payload has no tone keys |
| TC-17 | AC-13 | unit | **Given** `check_min_negativity` and `SubscriptionFilter` **When** the value is `-0.1`, `100.1`, NaN, infinity, `True` or `"8"` **Then** `InvalidNegativity` / `InvalidFilter` is raised; `0`, `100`, `8`, `9.7` and `None` pass |
| TC-18 | AC-13 | integration | **Given** a live app **When** `search_articles` and `semantic_search` get `min_negativity=101`; `GET /api/articles?min_negativity=-1` and `=abc`; and `POST /api/subscriptions {"min_negativity": 101}` and `{"min_negativity": true}`; and an MCP call sends `"abc"`, `"8"` or `true` **Then** MCP answers `invalid_filter` for the range case and a tool error for the non-number; REST and the subscription POST answer 422; nothing is stored |
| TC-19 | AC-14 | integration | **Given** rows differing in theme, domain, title and time **When** `search` and `list_new` get `min_negativity` together with `theme`, `domain`, `text` and a time range **Then** only rows satisfying every filter are returned |
| TC-20 | AC-15 | unit | **Given** the app **When** `create_app().openapi()` is generated **Then** it equals the committed `apps/web/src/lib/api/openapi.json`, and that document lists `include`, `min_negativity`, the optional tone keys on the feed articles and the three new detail fields |
| TC-21 | AC-15 | unit (web) | **Given** generated types where a subscription filter value is `string \| number` **When** `Subscriptions` renders a subscription with `{ min_negativity: 8 }` **Then** the row shows `min_negativity: 8` and the project's type check and style check pass |

**Regression updates (not new ACs):** two assertions in `apps/api/tests/unit/test_subscriptions.py` compare `as_query()` to a three-key dict; they gain `"min_negativity": None` in T-06. Any other test that fails because a default payload changed is a bug (AC-1), not a test to edit.

## 3. Manual checks

None: all 15 ACs are `Verify: auto`. The live check at verify time (not an AC) is to call `search_articles(min_negativity=8, include=["tone_neg"])` against the dev stack and read three results.

## 4. Measurements (provisional targets: measure first, no pass/fail)

| ID | What | How |
|---|---|---|
| M-1 | Latency of `search_articles` with `min_negativity` | `EXPLAIN (ANALYZE)` on the dev table for the filter alone, with a 24-hour time range, and with a theme; record rows scanned and milliseconds. Decides whether the `tone_neg` index stays in the backlog (spec §7) |
| M-2 | Payload growth of a 200-article page | Byte size of a `list_new_articles(limit=200)` response without `include`, with `["tone_neg"]` and with all four; record the percentage |
