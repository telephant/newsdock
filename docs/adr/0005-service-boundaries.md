# ADR-0005: One deployable per responsibility (5 Python apps + web)

Status: **Accepted 2026-10-04** (user decision during the roadmap discussion; recorded 2026-10-05 in `/spec-design foundation`, spec D-4)

## Context
The user asked whether two backend services would do: one Python service for fetch, process, clean and store, and one for the platform API. The M1 design already separates serving (`api`) from the pipeline, but splits the pipeline into three Kafka clients (`ingester`, `processor`, `sink`) and keeps the demo `agent` isolated (AC-13).

## Options
1. `ingester`, `processor`, `sink`, `api`, `agent` (Python) + `web` (current design).
2. Two backend services: `pipeline` (ingester, processor, sink as separate entrypoints of one codebase) + `api`; `agent` and `web` unchanged.
3. One backend monolith.

## Decision
Option 1. Each consumer group, the API and the agent are separate containers with their own restart and failure domain; the user chose this knowing option 2 exists.

## Consequences
+ Matches the Kafka learning goal (visible consumer groups, independent restarts); the agent stays isolated (AC-13); simple per-app tests. − Six Dockerfiles and compose entries and more boilerplate, reduced by the M0 skeleton and shared `newsdock_core`. Merging apps later is cheap because logic lives in `domain/` and `newsdock_core`; revisit only if the boilerplate hurts.
