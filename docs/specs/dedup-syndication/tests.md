# dedup-syndication — Tests

Spec: [spec.md](spec.md) §6 · Design: [design.md](design.md) · Derived 2026-10-05.

## Test data and fakes

- **Real titles**: the existing M1 fixture `packages/core/tests/fixtures/gkg_sample.tsv` plus hand-made variant sets (case/whitespace/suffix) built from titles observed in `docs/specs/mvp/labels.csv` (e.g. the `| Wilts and Gloucestershire Standard` copy). New key-specific cases live as table-driven data inside the unit test, not as files.
- **Copies**: integration tests build `CleanArticle` copies programmatically (same title ± suffix, different URLs/slots/published_at) — no new fixture files.
- **Infra**: unit tests use fakes for the story repo/writer; docker-marked tests run against the compose Postgres (and API where needed), reusing the M1 per-module compose-project pattern. `make test-infra SCENE=sink|api` covers them.
- **Calibration** (not a TC): the T-01 spike runs `story_key` over the two saved live slots and records grouping % and eyeballed false merges in `plan.md`.

## Test cases

| TC | AC | Level | Given / When / Then |
|---|---|---|---|
| TC-1 | AC-1 | unit | Table-driven: case/whitespace variants, `| Site` and `- Site` suffixes, fixpoint chains (`"T - X | Site"`), threshold boundaries (remainder 24 vs 25 chars; segment 45 vs 46), NFKC forms → same key for variants of one title, different keys for different titles; empty-after-strip falls back |
| TC-2 | AC-2 | integration | Two copies (same normalized title, different URLs, 1 h apart) through the sink → exactly 1 `articles` row, 2 `article_sources` rows linked to it |
| TC-3 | AC-3 | integration | A stored story; a new-URL copy from a later slot within the window → no new article, +1 source |
| TC-4 | AC-4 | integration | Redelivering an already-stored URL (as both canonical and source cases) → no new rows in either table |
| TC-5 | AC-5 | integration | Same story key, `published_at` 3 days apart (window 48 h) → two separate canonicals |
| TC-6 | AC-6 | integration | Story with 3 sources: `get_article` and `GET /api/articles/{id}` return `source_count = 3` and all 3 `{url, domain, published_at}` |
| TC-7 | AC-7 | integration | Mixed store (grouped story, plain article, pre-feature NULL-key row): search/feed return each story once; `source_count` is 3 / 1 / 1 |
| TC-8 | AC-8 | integration | Cursor taken past a story; a new copy arrives; `list_new_articles(cursor)` → the story is not re-emitted (no new `seq`) |
| TC-9 | AC-9 | integration | 3 copies seeded; the agent loop (fake scorer) runs against the real API → exactly one analysis, attached to the canonical (lives in `infra/scripts/tests/test_story_agent.py`: cross-app, DR-7) |
| TC-10 | AC-10 | manual | Checklist: feed shows "N sites" badge only where `source_count > 1`; detail lists the sources as links |
| TC-11 | AC-10 | unit (web) | Feed renders the badge for `source_count: 3` and no badge for 1; detail renders the sources list with escaped text |
| TC-12 | AC-11 | integration | Canonical aged 8 d with sources; retention (injected clock) → canonical and all its sources gone |
| TC-13 | AC-12 | unit | `process_batch` over fakes returns/logs `canonicals created / copies grouped / url duplicates` counts that sum to the batch |
| TC-14 | AC-2 | unit | Both copies arrive in the SAME batch: the in-batch cache yields one canonical, no second DB insert attempt (fake story repo records calls) |

Coverage: every AC-1…AC-12 has ≥ 1 TC; no TC without an AC (validated in plan.md).

## Manual checklist

- **TC-10 (AC-10)** at `/spec-verify`: open the feed with live grouped data, confirm badge placement and the detail's source list.

## Measurements (provisional targets — recorded, not pass/fail)

| What | Target (guess) | How |
|---|---|---|
| Stored-article reduction | ≈ 14 % | AC-12 log summed over ≥ 1 live slot at verify |
| Agent LLM-call reduction | ≈ duplicate rate | agent batch log before/after on the same slot |
| False merges | ≈ 0 | hand-check every multi-source group from one live slot |
| Cross-slot published_at spread of real copies | < 48 h | max spread per group during the T-01 calibration (informs D-5) |
