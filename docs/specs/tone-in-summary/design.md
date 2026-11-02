# tone-in-summary — Design (M3b)

Spec: [spec.md](spec.md) · Detail (reference only): [design-detail.md](design-detail.md) · Diagrams: [diagrams/index.html](diagrams/index.html) · ADR: [0030](../../adr/0030-opt-in-article-fields-projected-at-the-boundary.md) (Accepted 2026-10-30)

**Reading order:** this file → the diagrams (each has a "Check" box) → the checklist at the bottom. Component ids start at C-60 (C-50…C-58 belong to what-happen). No new table, migration, setting or dependency.

The change is small on the data side (the four tone columns are already in every row the API loads) and careful on the contract side: the default payload must stay byte-for-byte the same, the filter must exist once, and the REST schema must show the new fields.

## 1. Components

| Id | Job | Where / notes |
|---|---|---|
| C-60 | Tone rules: field names, `parse_include`, `check_min_negativity`, the two error types | `domain/tone.py`; pure |
| C-61 | Records: four tone fields on `ArticleSummary` (never serialized by default), `to_json(include)`, `dump_page`, three more fields on `ArticleDetail`, documentation models for the REST schema | `domain/records.py` |
| C-62 | Article repo: fills tone fields only for requested names; `apply_filters(min_negativity=…)`; `search`, `list_new`, `summaries` take `include` | `adapters/repo.py`; the one filter implementation |
| C-63 | Semantic search: `SearchFilters.min_negativity`, both legs use `apply_filters`, hits carry the tone fields | `domain/semantic.py`, `adapters/semantic_repo.py` |
| C-64 | Service layer: passes `min_negativity` and `include` through `search` and `list_new` | `domain/service.py` |
| C-65 | Subscriptions: `min_negativity` in the saved filter, storage widened to numbers, stream query carries it | `domain/subscriptions.py`, `adapters/subscriptions_repo.py`, `adapters/sse.py`, `adapters/streaming.py` |
| C-66 | Surfaces: MCP `search_articles`, `semantic_search`, `list_new_articles`; REST `GET /api/articles`; error mapping | `adapters/http.py` |
| C-67 | Contract and docs: regenerated `openapi.json` and `types.ts`, a drift test, the web filter chip for a number, doc updates | `apps/web/src/lib/api/`, `features/subscriptions/`, `CLAUDE.md`, `docs/` |

Extension points (backlog, not built): `order=negativity`, an index on `tone_neg`, `min_negativity` on `list_new_articles`, `include` on streams.

## 2. Key flows

- **F-60 Read with tone** (diagram 2): the surface parses `include` (C-60) → the service passes it down → the repo copies only the requested tone numbers into each summary (C-62) → the surface writes `to_json(include)` (C-61). Without `include` nothing is copied and nothing is written.
- **F-61 Filtered search** (diagram 2): `min_negativity` is checked (C-60) → `apply_filters` adds `tone_neg >= :value` (C-62) in search, in both semantic legs (C-63) and in the REST feed.
- **F-62 Subscription** : the saved filter may hold `min_negativity`; the stream's cursor query (`list_new`) passes it to the same `apply_filters` (C-65).

## 3. Contracts

| Surface | New input | New output |
|---|---|---|
| MCP `search_articles`, `semantic_search` | `min_negativity: float`, `include: list[str]` | `articles[]` gain the requested tone keys |
| MCP `list_new_articles` | `include: list[str]` | same |
| REST `GET /api/articles` | `min_negativity`, `include=a,b` | same; schema documents the optional keys |
| Subscription body | `min_negativity: number` | `filter` may hold a number |
| `get_article`, `GET /api/articles/{id}` | none | `tone_pos`, `tone_neg`, `tone_polarity` added to `tone` |

Errors: unknown `include` name → MCP `invalid_include`, REST 422 `invalid_include`; `min_negativity` outside 0–100 → MCP `invalid_filter`, REST/subscription 422 `invalid_filter`. A non-number is rejected by the framework's own argument validation (MCP tool error, REST 422).

## 4. The tricky parts

1. **Default payload must not change** (AC-1). The four fields are `exclude=True` on the model, so any code that dumps a summary without asking for tone (streams, live feed, existing tests) keeps its exact output. Tone is added back only by `to_json(include)`.
2. **Absent versus null** (AC-7). `to_json` writes a requested key with `null` when the article has no value, and writes nothing for a name that was not requested.
3. **No FastAPI response round trip.** FastAPI re-validates a returned model against `response_model`, which would put the keys back or drop them. The REST feed therefore returns a `JSONResponse` it built with `to_json`, and documents the shape with `responses=` (ADR-0030).
4. **One filter** (AC-10). `apply_filters` gains the argument; search, list-new, both semantic legs and subscriptions all go through it.
5. **Boundary on a `real` column.** `tone_neg` is float4; the parameter is cast to `real` so `8.0`, `9.7` and every value typed with one decimal compare equal to a stored value of the same decimals **[verified: column type `real`]**.
6. **Subscription storage was `dict[str, str]`.** The saved filter is JSONB, so a number is stored as is; the Python types and the stream's key list widen. Old rows have only string values and keep working.
7. **Shared builders.** Semantic hits are built from `dict(summary)`, which carries all fields, so the tone numbers flow into `SemanticHit` without extra code.

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| Unknown `include` name | error, no articles (AC-6) |
| `min_negativity` below 0, above 100, NaN | error, nothing stored or returned (AC-13) |
| Article without tone | requested keys are `null`; never matches `min_negativity` |
| Old subscription rows | still load and match as before |
| Large page with all four fields | payload grows by four numbers per article; measured at verify |

## 6. Technology

Nothing new. SQLAlchemy 2 (`cast(…, REAL)`), pydantic 2 (`Field(exclude=True)`), FastAPI (`JSONResponse`, `responses=`) and FastMCP, all already used in `apps/api` **[verified: existing code]**. One ADR for the projection pattern.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1 | C-61 (excluded fields) |
| AC-2 | C-60, C-62, C-66 (F-60) |
| AC-3 | C-62, C-64, C-66 (F-60) |
| AC-4 | C-63, C-66 (F-60) |
| AC-5 | C-61, C-66 (F-60) |
| AC-6 | C-60, C-66 |
| AC-7 | C-61 |
| AC-8 | C-61, C-62 |
| AC-9 | C-62 (F-61) |
| AC-10 | C-62, C-63 (F-61) |
| AC-11 | C-62, C-66 (F-61) |
| AC-12 | C-65 (F-62) |
| AC-13 | C-60, C-65, C-66 |
| AC-14 | C-62 (F-61) |
| AC-15 | C-67 |

## 8. Questions to answer before approving this design

All six resolved 2026-10-30: recommended answers accepted (projection at the boundary, `real` cast, values as stored, `/api/live` unchanged, non-number on MCP uses the framework error, no index until measured).

- [x] Is projecting at the boundary (fields excluded by default, `to_json(include)`) the right shape, instead of always-on fields plus a stripping serializer? (tricky parts 1 to 3, ADR-0030)
- [x] Is casting the filter parameter to `real` the right way to make the boundary exact, accepting that a stored `9.69697` is not `>= 9.7`?
- [x] Do you accept tone numbers as stored, including float4 noise such as `9.699999809265137`, instead of rounding them? (spec D-9)
- [x] Is it fine that `GET /api/live` does not get `min_negativity` (it shares the subscription parser but only exposes `theme`, `domain`, `text`)?
- [x] Is it fine that a non-number `min_negativity` on MCP fails with the framework's own validation error rather than `invalid_filter`? (AC-13 wording changes to match)
- [x] Is "no index on `tone_neg` until measured" acceptable? (spec §7)
