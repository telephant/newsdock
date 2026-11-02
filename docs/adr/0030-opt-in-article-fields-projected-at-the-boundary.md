# ADR-0030: Opt-in article fields, excluded by default and projected at the boundary

Status: **Accepted 2026-10-30** (spec `tone-in-summary`, D-1; confirmed by the user during `/spec-design`)

## Context
Agents want the tone numbers in article lists (spec D-1, D-2, D-3), but the list payload is a contract: existing agents, the web client, the SSE streams and the live feed all receive the same `ArticleSummary`. The user chose an argument that decides which fields come back, with the default payload unchanged. Three code facts constrain how: semantic hits are built from `dict(summary)` (every field is copied), FastAPI re-validates a returned model against its `response_model` (a dump and a validate), and `ArticleSummary` is dumped in several places (MCP tools, REST, streams) that must not change.

## Options
- **(a) Fields excluded by default, added by `to_json(include)`, REST returns a `JSONResponse`.** Tone fields exist on the object (`Field(exclude=True)`, as `seq` already is) and the surface decides what to write.
- **(b) Always-on optional fields plus a serializer that drops the unrequested ones.** Needs per-instance state that does not survive `dict(summary)` or FastAPI's response round trip.
- **(c) Separate response models per request shape** (`ArticleSummaryWithTone`). Duplicates every route and tool and splits the contract.
- **(d) Always return tone.** Simplest, but changes every payload and every agent's token cost.

## Decision
**(a).** The four tone fields are `exclude=True` on `ArticleSummary`; the repos fill only the requested ones; `to_json(include)` writes them (a requested field with no value is `null`). The REST feed returns a `JSONResponse` built with `to_json` and documents the optional keys with `responses=` and a documentation-only model. MCP tools already return dicts, so they call `to_json`/`dump_page` directly.

## Consequences
+ The default payload is unchanged by construction: nothing that dumps a summary without asking can leak tone (AC-1), including the streams and live feed.
+ No dependence on pydantic's "fields set" bookkeeping or on FastAPI's response round trip.
+ The same pattern can carry other opt-in fields later (for example `word_count`, `persons`) by adding names to a tuple.
− The REST feed handler no longer returns a model, so FastAPI does not validate its output; the schema is documentation and a contract test (AC-15) keeps it honest.
− Two models describe the feed (the real one and the documentation one); they must be kept in step.
− Float noise from the `real` column (for example `9.699999809265137`) is passed through as stored (spec D-9).
