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

## Amendment 2026-10-09 (approved by the user at /spec-verify; spec D-6, AC-13)
Live data (3 GDELT slots, 4,110 copies) showed generic titles merging different pages of one site: 6 of 261 multi-source groups, 17 copies ("The Miami Student" staff pages, "Subscribe to the Townsville Bulletin", "China Daily Website...", boilerplate RNS "Company Announcement" titles). **Decision:** a copy joins a story only if the story holds no same-domain copy with a different *page signature* (last path segment lowercased + sorted query); copies from other domains always join. Candidates are all same-key canonicals in the window, oldest first; the copy joins the first compatible one, otherwise starts a new story (story keys are therefore not unique). Effect on the same slots: false merges 17 → 0; grouping 22.4 % → 21.6 % (URL variants with different ids, e.g. rttnews, israelnationalnews, now stay separate as before M2a). Rejected alternatives: title-contains-domain test (misses boilerplate titles), full-path equality (splits iHeart stations that add a path prefix).

## Consequences
+ Deterministic, pure, unit-testable key; idempotent per-copy writes; cascade retention for free. − Thresholds and window are heuristics: too tight → missed groupings (harmless), too loose → false merges (bad, hence the conservative window); reworded titles are not grouped until M3 embeddings.
