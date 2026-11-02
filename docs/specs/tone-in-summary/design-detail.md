# tone-in-summary — Design detail

Reference only: not required reading for approving the design (see [design.md](design.md)).

## 1. Tone rules (C-60) — `apps/api/src/newsdock_api/domain/tone.py`

```python
TONE_FIELDS: tuple[str, ...] = ("tone", "tone_pos", "tone_neg", "tone_polarity")


class InvalidInclude(ValueError): ...  # MCP invalid_include, REST 422 invalid_include


class InvalidNegativity(
    ValueError
): ...  # MCP invalid_filter, REST/subscription 422 invalid_filter


def parse_include(raw: Iterable[str] | str | None) -> tuple[str, ...]:
    """None or empty -> (). A str is a comma list (REST). Names are stripped, duplicates
    dropped, order kept; any name not in TONE_FIELDS raises InvalidInclude."""


def check_min_negativity(value: float | None) -> float | None:
    """None -> None. bool, NaN, infinity or outside 0..100 raise InvalidNegativity."""
```

`bool` is rejected because JSON `true` would otherwise pass as `1`.

## 2. Records (C-61) — `domain/records.py`

```python
class ArticleSummary(BaseModel):
    ...existing fields...
    tone: float | None = Field(default=None, exclude=True)
    tone_pos: float | None = Field(default=None, exclude=True)
    tone_neg: float | None = Field(default=None, exclude=True)
    tone_polarity: float | None = Field(default=None, exclude=True)

    def to_json(self, include: Sequence[str] = ()) -> dict[str, Any]:
        out = self.model_dump(mode="json")
        for name in include:                    # names are already validated
            out[name] = getattr(self, name)     # None -> null
        return out
```

`exclude=True` keeps the existing `seq` precedent: the fields exist on the object, never reach a default dump. `SemanticHit` inherits `to_json`.

`dump_page(page, include)` returns `page.model_dump(mode="json", exclude={"articles"}) | {"articles": [a.to_json(include) for a in page.articles]}` for `NewArticlesPage`, `FeedPage` and `SemanticResult` (all three have `articles`).

`ArticleDetail` gains `tone_pos`, `tone_neg`, `tone_polarity` as ordinary `float | None` fields, filled by `SqlArticleRepo.get`.

Documentation models (schema only, never instantiated by a handler): `ArticleSummaryTone(ArticleSummary)` redeclares the four fields as plain optional fields, and `FeedPageTone` holds `articles: list[ArticleSummaryTone]` and `next_before`. They exist so `openapi.json` shows `tone?: number | null` etc. on the feed.

## 3. Repo (C-62) — `adapters/repo.py`

```python
def _summary(row, scores=None, source_count=1, include=()) -> ArticleSummary:
    tone = {name: getattr(row, name) for name in include}  # only what was asked
    return ArticleSummary(..., **tone)
```

`search`, `list_new` and `summaries` take `include: Sequence[str] = ()` and pass it to `_summary`. No extra SQL: `select(Article)` already loads the columns.

`apply_filters` gains `min_negativity: float | None = None`:

```python
if min_negativity is not None:
    statement = statement.where(Article.tone_neg >= cast(literal(min_negativity), REAL))
```

`NULL >= x` is not true in SQL, so articles without `tone_neg` drop out with no extra clause. The cast makes the comparison float4 against float4 (a float8 parameter would compare a stored `9.7f` as `9.69999981…` against `9.7`). The value is bound as a parameter, never formatted into SQL.

`list_new` already accepts `theme`, `domain`, `text` and calls `apply_filters`; it gains `min_negativity` for subscriptions. `search` keeps its keyset pagination (`before`) unchanged.

## 4. Semantic (C-63)

`SearchFilters` (a frozen dataclass of `time_from, time_to, theme, domain`) gains `min_negativity`. `vector_leg` and `keyword_leg` pass `filters.min_negativity` to `apply_filters`. `SemanticService.search` takes `min_negativity` and `include`; `self._repo.summaries(ids, include)` fills the tone fields; the existing `SemanticHit.model_validate({**dict(summary), "score": …, "matched_by": …})` carries them because `dict(model)` yields every field including excluded ones. The result is written with `dump_page`.

## 5. Service (C-64)

`ArticleService.search(..., min_negativity=None, include=())` and `list_new(..., min_negativity=None, include=())` forward to the repo. `check_min_negativity` runs in the surface, not here, so the service only ever sees valid values.

## 6. Subscriptions (C-65)

- `SubscriptionFilter` gains `min_negativity: float | None` with a `mode="before"` validator that rejects `bool` and `str`, then `check_min_negativity`. `extra="forbid"` stays.
- `as_query()` returns `dict[str, str | float | None]` with the new key; `as_json()` stores only given keys, so an old filter serializes exactly as before.
- `SubscriptionRecord.filter` and `AdminSubscription` become `dict[str, str | float]`; `SubscriptionStore.create(filter_json: dict[str, str | float])`; the JSONB column needs no migration.
- `adapters/sse.py` builds the stream query from `("theme", "domain", "text", "min_negativity")`; `adapters/streaming.py` forwards it to `service.list_new`.
- `adapters/live.py` keeps its three query parameters; its `as_query()` result now carries `min_negativity=None`, which `list_new` accepts.
- A subscription is still just a filter: stream payloads do not take `include` (spec D-8).

## 7. Surfaces (C-66) — `adapters/http.py`

MCP tools (all return `dict`):

```python
# Strict, so "8" and true are rejected instead of coerced to 8.0 and 1.0 (spike.md (c)).
Negativity = Annotated[float | None, Field(strict=True)]

def search_articles(..., min_negativity: Negativity = None,
                    include: list[str] | None = None): ...
def semantic_search(..., min_negativity: Negativity = None,
                    include: list[str] | None = None): ...
def list_new_articles(ctx, cursor=None, limit=None, include: list[str] | None = None): ...
```

Each tool parses with `parse_include` and `check_min_negativity` inside a `try`, turning `InvalidInclude` into `ToolError("invalid_include: …")` and `InvalidNegativity` into `ToolError("invalid_filter: …")`, then returns `dump_page(...)` (or `{"articles": [a.to_json(inc) for a in articles]}` for `search_articles`, whose shape stays as today). Tool docstrings describe the two arguments.

REST feed:

```python
@app.get("/api/articles", response_model=None,
         responses={200: {"model": FeedPageTone}}, dependencies=[Depends(guards.read)])
def rest_articles(..., min_negativity: float | None = None,
                  include: str | None = None) -> JSONResponse: ...
```

Errors raise `HTTPException(422, detail="invalid_include" | "invalid_filter")`. The handler returns `JSONResponse(dump_page(FeedPage(...), inc))`. The REST detail route and `get_article` need no handler change.

## 8. Contract and docs (C-67)

- Regenerate: `DATABASE_URL=postgresql+psycopg://x:x@localhost/x uv run python -m newsdock_api.openapi > apps/web/src/lib/api/openapi.json`, then `pnpm --dir apps/web run generate:api`, then format as the repo checks.
- New test `apps/api/tests/unit/test_openapi_contract.py`: `create_app().openapi()` equals the committed `openapi.json` (AC-15). `types.ts` is checked in verify with `git diff --exit-code` after regenerating.
- `features/subscriptions/Subscriptions.tsx` renders `Object.entries(sub.filter)`; with values typed `string | number` it must still compile and show `min_negativity: 8`. It already renders each value with `String(value)`, so the screen needs no code change.
- **Found at T-09 (2026-10-30):** the generated document no longer contains the schemas `ArticleSummary` and `FeedPage` (only the feed used them; it is now documented as `ArticleSummaryTone` / `FeedPageTone`). The hand-written wrapper `apps/web/src/features/feed/api.ts` aliased the old names, so it now points its exported `ArticleSummary` and `FeedPage` types at the new schemas; the exported names are unchanged, so no other web file changes.
- Docs to update in the same edit: `CLAUDE.md` (fixed names: MCP arguments, `ArticleSummary` optional fields, Status line), `docs/roadmap.md`, the `semantic-search` filter notes, and the API/MCP descriptions that list filters.

## 9. Failure table (full)

| Failure | Detected by | Result |
|---|---|---|
| Unknown include name | `parse_include` | MCP `invalid_include`; REST 422 `invalid_include`; no query runs |
| `min_negativity` < 0, > 100, NaN, infinity | `check_min_negativity` | MCP `invalid_filter`; REST/subscription 422 `invalid_filter` |
| Non-numeric `min_negativity` | framework validation | MCP tool error; REST 422 |
| `true`/string in a subscription body | `SubscriptionFilter` validator | 422 |
| Article with NULL tone | SQL `NULL >= x` | not matched; requested keys `null` |
| Pre-change subscription rows | `SubscriptionFilter` accepts missing key | unchanged behaviour |
| Semantic embedding down + `min_negativity` | existing degrade path | hybrid keyword leg applies the same filter; vector fails as before |
| Row removed by retention between legs and summaries | existing `if i in summaries` | hit skipped as today |

## 10. Security

- No new data source, route or permission: tone is already readable through `get_article`. The same guards apply (`guards.read`, agent key).
- All values are bound parameters; field names come from a fixed tuple, never from input.
- `include` cannot reach any column outside `TONE_FIELDS`.
- The error text never echoes more than the offending name or number.
