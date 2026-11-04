# Plan — events-grouped-copies

## Plan validation (2026-11-04)

| Check | Result |
|---|---|
| AC → test (AC-1…AC-10 each have a TC; TC-1…TC-12 each have an AC) | pass |
| AC → design (`design.md` coverage table) | pass |
| AC → task (table below) | pass |
| Names identical across docs (`derived`, migration `0013`, ADR-0038, `link_copy_mentions`, `link_mentions_of`) | pass |
| No doc treats a Proposed ADR as decided (ADR-0038 Accepted 2026-11-04) | pass |
| Backlog items leaked into scope | none |
| Open questions / unchecked items | none |

## Spike first

**T-01** measures the biggest unverified claim before any code: how many derived rows the link statement would create on real data (assumed up to about 29% more mention rows) and how long the backfill `SELECT` takes. It is read-only. If the numbers are far off, stop and revisit ADR-0038 option (c).

## Tasks (walking skeleton: data → write path → read path → docs)

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: size and time of the link statement (read-only) | measurements | none |
| T-02 | Migration 0013 `derived` column + backfill, model field | AC-3 | T-01 |
| T-03 | Sink adapter: link statement, real-beats-derived upsert | AC-1, AC-2, AC-5, AC-7, AC-8 | T-02 |
| T-04 | Sink domain wiring (ports and calls) | AC-1, AC-2, AC-7 | T-03 |
| T-05 | API: `mention_count` ignores derived rows; MCP and REST checks | AC-4, AC-5, AC-6, AC-9, AC-10 | T-02 |
| T-06 | Docs: events-mentions spec/design notes, `CLAUDE.md`, roadmap, ADR-0033 link | all | T-05 |

Milestones: after T-02 backfill works (AC-3); after T-04 new data links itself (AC-1, AC-2, AC-7, AC-8); after T-05 agents see it (AC-4, AC-5, AC-6, AC-9, AC-10).

## Effort

Small: T-01 0.5 h, T-02 1 h, T-03 2 h, T-04 1 h, T-05 1.5 h, T-06 1 h (about one working day) **[assumption]**.

## Definition of Done

Tests first and green (`make test APP=sink`, `make test APP=api`, docker modules through `make test-infra` with the dev stack stopped); `make check` green; docs and ADRs updated in the same edit; no secrets; nothing outside the milestone.
