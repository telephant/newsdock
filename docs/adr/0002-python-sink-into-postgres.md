# ADR-0002: Python sink consumer writes Postgres (separate from the processor)

Status: **Accepted 2026-10-04**

## Context
The processor produces clean rows to `gkg.clean`; something must write them to Postgres. Keeping the writer separate keeps the processor stateless and lets retention and `seq` assignment live with one single writer.

## Options
1. Processor → `gkg.clean` → Python consumer → Postgres.
2. Processor writes Postgres directly.

## Decision
Option 1. The sink also owns retention and assigns `seq` (single writer → monotone cursor).

## Consequences
+ Fewer jars, easy tests, at-least-once + `ON CONFLICT DO NOTHING`. + Replayable topic. − One extra process and hop (latency of seconds). 
