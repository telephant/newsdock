# tone-in-summary — Spike (T-01)

Run 2026-10-30 on the worktree's own `.venv` (FastAPI 0.142.2, pydantic 2.13.5, SQLAlchemy 2.1.3, `mcp` `MCPServer`), with throwaway scripts outside the repo. No production code changed. All four claims were checked this session, so they are tagged **[verified]**.

**Verdict: the design holds.** One refinement to the MCP argument types (below); ADR-0030 is unchanged.

## (a) REST schema and `JSONResponse` — holds **[verified]**

A route declared `response_model=None, responses={200: {"model": PageTone}}` that returns a `JSONResponse` built with `to_json`:

- default call: `{"next_before": null, "articles": [{"article_id": "a", "title": "t"}, …]}` — no tone key;
- `include=tone_neg`: `"tone_neg": 9.5` on the article that has it and `"tone_neg": null` on the one that does not;
- `openapi()`: the 200 response is `{'$ref': '#/components/schemas/PageTone'}` and `SummaryTone` lists `article_id, title, tone, tone_neg`; the excluded `seq` is absent. So the documentation-only twin gives the schema and the handler is not re-validated.

## (b) `dict(model)` and excluded fields — holds **[verified]**

`model_dump()` of a model with `Field(exclude=True)` fields gave `['article_id', 'title']`; `dict(model)` gave `['article_id', 'seq', 'title', 'tone', 'tone_neg']`, and a subclass built from that dict kept all of them. So the existing `SemanticHit.model_validate({**dict(summary), …})` assembly carries the tone fields with no extra code (design tricky part 7).

## (c) MCP argument validation — holds, with one refinement **[verified]**

Tool typed `float | None` / `list[str] | None`, called through `MCPServer.call_tool`:

| Input | Result |
|---|---|
| `min_negativity` 8, 8.5, omitted | accepted |
| `101` | our `ToolError("invalid_filter: …")` |
| `"abc"` | framework `ToolError: Error executing tool …: Input should be a valid number` |
| **`"8"`** | **silently accepted as 8.0** |
| **`true`** | **silently accepted as 1.0** |
| `include` as a bare string `"tone_neg"` or `[1]` | framework `ToolError` (no coercion) |

**Refinement:** declare the argument `Annotated[float | None, Field(strict=True)]`. With it `"8"`, `true` and `"abc"` all fail with a tool error, `8` and `8.5` still pass, and the published input schema is unchanged (`anyOf number, null`). Design-detail §7 and T-07 now say so; REST needs no change because query strings are text by nature and `true` fails float parsing with a 422.

## (d) The `real` cast — holds **[verified]**

On a side Postgres (own compose project, removed afterwards; no leftover container) with a `real` column holding 8.0, 9.5, 9.7, 12.5, 0.1, 33.3:

| Parameter | float8 `>=` matches its own stored value | `cast(…, REAL)` matches |
|---|---|---|
| 8.0, 9.5, 12.5, 0.1 | yes | yes |
| **9.7** | **no** | yes |
| **33.3** | **no** | yes |

So without the cast, `min_negativity=9.7` would drop an article whose `tone_neg` is exactly 9.7. The cast is required (design tricky part 5).

**Side finding:** a stored `real` 9.7 read back through SQLAlchemy and psycopg is `9.7`, not `9.699999809…`. The float noise that design checklist question 3 worried about did not appear in this read path; the decision "as stored" stands and costs nothing.

## Other note

The job's shared temp directory held an old `inspect.py` that shadowed the stdlib when a script ran from there. Spike scripts were run with `python -I`. Not a project issue.
