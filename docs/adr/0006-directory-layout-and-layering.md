# ADR-0006: Directory layout, src layout and domain/adapters layering

Status: **Accepted 2026-10-05** (user decisions D-6, D-7, D-8 in `/spec-init foundation`)

## Context
Future code needs fixed places to live and import rules that can be checked mechanically. Rules DR-1…DR-13 are in `docs/specs/foundation/spec.md` §6.

## Options
1. Flat apps, rules only on imports.
2. Layering only where there is logic (processor, sink, api).
3. `src/newsdock_<app>/` with `domain/` + `adapters/` in every Python app, enforced in `make check`.

## Decision
Option 3. Python packages are prefixed `newsdock_` (no clashes with generic names), `domain/` imports only stdlib, pydantic and `newsdock_core`, `adapters/` owns all I/O, apps never import each other, `newsdock_core` imports no app and no I/O library, env is read only in `config.py`. Enforcement tools: ADR-0007.

## Consequences
+ Uniform shape across five apps, logic testable without Kafka or Postgres, violations fail CI. − Some boilerplate in tiny apps (ingester, agent). Changing a rule needs an ADR and the user's approval.
