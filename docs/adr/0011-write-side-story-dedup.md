# ADR-0011: Write-side canonical story dedup in the sink

Status: **Accepted 2026-10-05** (user decision D-1 at `/spec-init dedup-syndication`, chosen over the recommended read-side grouping)

## Context
~14 % of GKG rows are republications of the same wire story (same title, different URL) **[verified on two live slots]**. M1 dedups by URL only, so every consumer sees each story up to ~10×.

## Options
1. Read-side grouping: store unchanged; API groups at query time. Non-destructive, reversible; every read pays the grouping cost; store keeps growing with copies.
2. **Write-side canonical: the sink stores one `articles` row per story and every copy as an `article_sources` row.** Store and all consumers see stories once; merges are irreversible (a copy never becomes a full article again) and the canonical is "first copy wins".
3. UI-only collapse: cheapest; agent and MCP consumers still see duplicates.

## Decision
Option 2, by user choice (risk of irreversible merges and syndicate-as-canonical accepted; every copy's data is still kept on the source row, so nothing is dropped).

## Consequences
+ One row per story everywhere: feed, cursor, agent (~14 % fewer LLM calls), metrics. + Copies remain queryable with provenance. − False merges need the window guard (ADR-0012) and a backlog repair job; canonical quality ("first wins") is a backlog refinement; M1's per-URL article identity now applies only to canonicals.
