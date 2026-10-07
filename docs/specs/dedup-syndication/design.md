# dedup-syndication — Design (Milestone 2a)

Status: **approved** · 2026-10-05 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (each diagram has a "Check" box) → ADR-0011, ADR-0012 in `../../adr/` → answer the checklist at the bottom.

## 1. Components (ids continue the M1 numbering; unchanged components not listed)

| Id | Component | Change | Notes |
|---|---|---|---|
| C-10 | Story keyer (`newsdock_core.stories`) | **new** | Pure function `story_key(title)`: NFKC, lowercase, collapse whitespace, fixpoint-strip trailing `| Site` / `- Site` segments (ADR-0012) |
| C-4 | Sink | **changed** | Groups by `(story_key, published_at ± window)`: first copy → canonical `articles` row; every copy → `article_sources` row; logs the dedup ratio per batch |
| C-5 | PostgreSQL | **changed** | `articles.story_key` (nullable: pre-feature rows stay NULL, D-4) + new table `article_sources` (PK `url_hash`, FK → articles ON DELETE CASCADE) |
| C-6 | API | **changed** | Summaries gain `source_count`; detail gains `sources[]`; search/list semantics otherwise unchanged (they already return only `articles` rows = canonicals) |
| C-8 | Web UI | **changed** | Feed badge "N sites" when `source_count > 1`; detail lists sources |
| C-7 | Demo agent | unchanged | Sees only canonicals → scores once per story (D-3) for free |

## 2. Key flows

- **F-5 Grouping write:** `gkg.clean` → C-4: compute `story_key` (C-10) → canonical lookup in window → insert canonical+source or source only. (Sequence diagram 2)
- **F-6 Story browse:** C-8 → C-6 `GET /api/articles` (`source_count`) → detail with `sources[]`. (Component diagram 1)
- **F-7 Story expiry:** retention deletes old canonicals; sources cascade (AC-11). (State diagram 4)

## 3. Contracts (deltas only)

**`articles`** += `story_key text NULL` (NULL = pre-feature row, never groups; all rows remain canonicals by construction).

**`article_sources`** (new)

| Column | Type | Notes |
|---|---|---|
| url_hash | text PK | same hashing as articles (public id of the copy) |
| article_id | text NOT NULL FK → articles(url_hash) ON DELETE CASCADE | the canonical |
| url, domain | text / text NULL | per-copy values |
| slot, gkg_record_id | text | provenance |
| published_at | timestamptz | the copy's own timestamp |
| ingested_at | timestamptz default now() | |

The canonical's own URL also gets a source row, so `source_count` = number of copies (AC-2).

**API deltas:** summary `+ source_count: int`; detail `+ sources: [{url, domain, published_at}]`, `+ source_count`. MCP tools keep their names; only output shapes grow (additive).

**Config:** `NEWSDOCK_STORY_WINDOW_HOURS` (sink, default 48, D-5).

## 4. Tricky parts

- **Consistent keys across variants:** suffix stripping runs to a **fixpoint**, so `"T"`, `"T | SiteA"`, `"T - SiteB"` all converge to the same key even when `T` itself contains a dash segment (ADR-0012 thresholds: strip only if the remainder ≥ 25 chars and the segment ≤ 45 chars).
- **Window guard (AC-5):** canonical lookup is `story_key = :k AND published_at BETWEEN :p - window AND :p + window`; same key outside the window starts a new story. Index `(story_key, published_at)`.
- **No races:** C-4 stays the single writer (ADR-0002), so lookup-then-insert needs no locking; within a batch, grouping happens in memory first.
- **Idempotency (AC-4):** both inserts are `ON CONFLICT DO NOTHING` on `url_hash` — a redelivered copy touches nothing; URL-level dedup (M1 AC-6) is preserved verbatim.
- **Cursor (AC-8):** `seq` exists only on `articles`; a late copy adds a source row, never a new `seq`, so `list_new_articles` cannot re-emit the story.
- **Mixed rows (D-4):** pre-feature rows have `story_key NULL` and no sources; reads treat them as 1-source stories (`source_count` falls back to 1). The 7-day retention removes them within a week.
- **Retention by canonical age:** a story dies when its *canonical* ages out, even if copies kept arriving; accepted and documented (fresh copies of week-old stories are rare wire behavior **[assumption]**).

## 5. Top failure modes

| Failure | Effect | Handling |
|---|---|---|
| False merge (two stories, one key, same window) | wrong grouping, analyses attach to one canonical | window guard + spot-check in verify; repair job is backlog |
| Redelivery after partial batch | duplicate copies re-processed | both inserts conflict-do-nothing (AC-4) |
| Poison source row (NUL etc.) | batch fallback | unchanged M1 row-by-row → dlq `bad_field` |
| Canonical expired, copy arrives | new canonical with fresh window | correct: it's news again after a week |
| Pre-feature row matches a new copy's title | no grouping (NULL key) | accepted (D-4); converges via retention |

## 6. Technology

No new dependencies: Python stdlib `unicodedata` for NFKC **[memory: stdlib, stable]**; existing SQLAlchemy 2 ORM + Alembic (revision `0003`, forward-only); existing FastAPI/MCP/Next.js surfaces. Diagrams: Mermaid 11.15 (cdnjs) **[verified 2026-10-04]**.

## 7. AC coverage

| AC | Covered by | Where |
|---|---|---|
| AC-1 | C-10 | `story_key` fixpoint normalization |
| AC-2 | C-4, C-5 | F-5 canonical+sources insert |
| AC-3 | C-4, C-5 | F-5 window lookup across slots |
| AC-4 | C-4, C-5 | ON CONFLICT on both tables |
| AC-5 | C-4, C-5 | window guard in the lookup |
| AC-6 | C-6 | detail `sources[]` + `source_count` |
| AC-7 | C-6 | summaries with `source_count` (canonicals only by construction) |
| AC-8 | C-6 | cursor on `articles.seq` only |
| AC-9 | C-7 (unchanged) | agent sees canonicals only |
| AC-10 | C-8 | feed badge + detail source list |
| AC-11 | C-4, C-5 | FK ON DELETE CASCADE from retention delete |
| AC-12 | C-4 | per-batch dedup-ratio log line |

## 8. Questions to answer before approving this design

- [x] ADR-0011: write-side canonical dedup recorded as decided at /spec-init (D-1, user 2026-10-05).
- [x] ADR-0012 accepted as proposed (user 2026-10-05).
- [x] No backfill; NULL-key rows read as 1-source stories for the overlap week (user 2026-10-05).
- [x] Retention stays on the canonical's ingested_at; whole story expires with it (user 2026-10-05).
- [x] API field names `source_count` / `sources` fixed (accepted with ADR-0012, 2026-10-05).
