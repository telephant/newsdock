# ADR-0032: Events and Mentions ride the existing pipeline, tagged by kind

Status: **Accepted 2026-11-02** (spec `events-mentions`; confirmed by the user during `/spec-design`, together with one sink loop for three topics and no back-fill of slots missed before the feature)

## Context
GDELT publishes Events (61 columns) and Mentions (16) next to GKG in each slot. The pipeline is hard-wired to GKG: `RawMessage` has no file type, the ingester and processor each use one topic, `route()` always calls `parse_row`, and `ingest_slot` is keyed by slot alone and read by `/api/health`. Topic names are fixed in `CLAUDE.md` (`gkg.raw`, `gkg.clean`, `gkg.dlq`) and checked by `check_config.py`. The three files of a slot become available independently (404 quirk, spec §3).

## Options
- **(a) Same raw and dead-letter topics, a `kind` field on the messages, two new clean topics, a separate `ingest_file` table.** GKG path and `ingest_slot` untouched.
- **(b) Separate pipelines per file type** (`events.raw`, `events.clean`, `events.dlq`, same for mentions; a second ingester loop). Cleanest isolation, most topics, services and config.
- **(c) One generic "gdelt file" abstraction replacing the GKG types.** Cleaner end state, rewrites working, verified code.
- **(d) Direct load from the ingester into Postgres, no Kafka for the two new files.** Fewest moving parts, but breaks the one-path rule and the processor/sink separation.

## Decision
**(a)**. `RawMessage` and `DlqMessage` get `kind` (default `gkg`, so existing messages stay valid); non-GKG keys are `slot:kind:row_no`; the processor dispatches on `kind` and writes `events.clean` and `mentions.clean`; the sink subscribes to the three clean topics; `ingest_file(slot, kind)` holds Events and Mentions state while `ingest_slot` stays GKG-only.

## Consequences
+ The working GKG path, its topic names and `/api/health` do not change; the new work is additive (new tables, new topics).
+ A missing Events or Mentions file can never block GKG (AC-4).
+ One raw and one dead-letter topic stay easy to inspect.
− `gkg.raw` and `gkg.dlq` now carry non-GKG lines; the names mislead until a later rename (a decided name, so it needs the user's approval).
− The sink loop handles three topics; a stuck Mentions batch holds offsets of the other two.
− `check_config.py`'s banned-literal list must be extended to the two new topic names.
