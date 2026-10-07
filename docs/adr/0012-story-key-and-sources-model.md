# ADR-0012: Story key normalization and the article_sources model

Status: **Accepted 2026-10-05** (user confirmed at `/spec-design dedup-syndication`; spec D-2/D-5 fixed the directions, this fixes the numbers and shapes)

## Context
Copies of one story differ by case, whitespace and a trailing `| Site Name` / `- Site Name` suffix **[verified in labels.csv and research samples]**. Grouping needs a deterministic key, a guard against unrelated stories sharing a title, and a place to keep each copy.

## Options
**Key:** (a) exact title; (b) **NFKC + lowercase + whitespace-collapse + fixpoint suffix-strip** (strip a trailing ` | seg` / ` - seg` only when the remainder keeps ≥ 25 chars and the segment is ≤ 45 chars; repeat to fixpoint, max 3); (c) fuzzy/embeddings (M3).
**Guard:** same key groups only when `published_at` is within ± `NEWSDOCK_STORY_WINDOW_HOURS` (default 48) of the canonical.
**Sources:** (i) separate `article_sources` table, PK `url_hash`, FK → canonical with CASCADE; (ii) JSON array on the article row (no per-copy idempotency); (iii) self-referencing `articles.canonical_id` (every copy stays a full row — closer to read-side).
**Canonical:** first copy wins (no quality ranking in this milestone).

## Decision
(b) + 48 h window + (i) + first-copy-wins. Thresholds 25/45 chosen from observed suffixes ("Wilts and Gloucestershire Standard" = 36 chars) vs. real in-title dashes; implemented as `newsdock_core.stories.story_key()`; the thresholds are constants there with table-driven tests, cheap to retune.

## Consequences
+ Deterministic, pure, unit-testable key; idempotent per-copy writes; cascade retention for free. − Thresholds and window are heuristics: too tight → missed groupings (harmless), too loose → false merges (bad, hence the conservative window); reworded titles are not grouped until M3 embeddings.
