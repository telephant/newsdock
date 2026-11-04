# Spec — events-grouped-copies (M3e, follow-up of M3c)

## 0. Review guide

- Today an article's `events` come from `mentions.url_hash = article id`. Only canonical articles are in `articles`; a story's grouped copies live in `article_sources`, so events and mentions that name a copy never reach the canonical. In the sample slot: 26 of 996 events and 727 of 2,514 mentions (events-mentions verify F-1, ADR-0033 consequence).
- This milestone makes the canonical article carry those events too, by **writing** the link when data arrives or is grouped (decided), with a backfill for rows already stored.
- Review order: §3 reality → §6 ACs → Decisions. Platform only (sink, migration, API unchanged in shape).

### Decisions

| ID | Decision | Status |
|---|---|---|
| D-1 | Where copies are joined to the canonical | Decided: at write time (2026-11-04) |
| D-2 | Meaning of `mention_count` | Decided: unchanged, counts real stored mentions of the event, not derived rows (2026-11-04) |
| D-3 | Which surfaces change | Decided: all that serve `events` (`get_article`, REST detail, `include=events` on lists and search) with no new argument (2026-11-04) |
| D-4 | ADR | Decided: a new ADR amends ADR-0033's consequence; the old text is kept and marked (2026-11-04, requested by the user) |
| D-5 | How derived rows are marked and kept out of `mention_count`, and how late grouping and backfill are handled | Decided: flagged derived rows in `mentions`, linked by the sink on both arrival orders, backfill in migration 0013, ADR-0038 (2026-11-04) |

**D-5.** Write time has three traps the design must solve: (1) a mention can arrive before its URL is grouped as a copy, so grouping must also link already-stored mentions; (2) rows already in the database need a one-time backfill; (3) if derived rows are plain `mentions` rows, `mention_count` (a row count per event) would grow, so they must be told apart or excluded. Recommendation: mark derived rows and exclude them from the count. The read-time join stays the fallback if write time proves fragile (it needs no migration).

**Open risks:** sink complexity and a write on the hot path; copies regrouped later (story merges) leaving stale links; extra storage (at most the 727 mentions per slot seen, about 29% more rows **[assumption]**, measure first).
**Prerequisites the user owns:** `make migrate` and rebuilding the `sink` and `api` images on the dev stack after merge.

## 1. Problem

An agent reading a story's canonical article misses events that GDELT attached to a syndicated copy of the same story, so `events` can be empty or short for a widely covered story.

## 2. Goals

- The canonical article's `events` include events found through its copies. Measured by re-running the F-1 count on a real slot: canonical articles that gain events through copies (5 of 778 before) show them.
- No change to payloads without `include`, to the meaning of `mention_count`, or to the per-article cap.
- Learning: keeping a derived link consistent with a table that changes after the fact.

## 3. Data/reality

- **[verified 2026-11-04]** `ArticleSource` (`article_sources`, PK `url_hash`, `article_id` → canonical, CASCADE) exists in `packages/db`, and `_events_for` in `apps/api/src/newsdock_api/adapters/repo.py` joins `Mention.url_hash IN article_ids` only.
- **[verified 2026-11-02]** (events-mentions verify F-1) 26 of 996 events and 727 of 2,514 mentions name a copy in the sample slot; only 5 of 778 canonicals would gain an event.
- **[assumption]** copies are grouped by the sink at insert time, so a mention can arrive before or after its URL is a copy.

## 4. Scope (walking skeleton)

**In:** link events of copies to the canonical at write time; relink when a URL becomes a copy; one-time backfill of stored rows; `mention_count` unchanged; retention covers derived rows; ADR amendment; events-mentions docs updated.
**Out:** read-time join, new API arguments, web screens, digest agent changes, serving copies as articles, the GDELT terms check.

## 5. Users and key flows

An agent calls `get_article` or a list/search tool with `include=["events"]` (or REST `include=events`) → the canonical shows the events of its copies too, once, with the usual fields.

## 6. Acceptance criteria

AC-1  Copy's mention shows on the canonical
  Given a canonical article and a grouped copy, and a stored mention of an event naming the copy
  When  the canonical is read with `include=events`
  Then  `events` contains that event
  Verify: auto

AC-2  Mention arrives before grouping
  Given a mention naming a URL that is not yet a copy, then that URL is grouped under a canonical
  When  the canonical is read with `include=events`
  Then  `events` contains that event
  Verify: auto

AC-3  Backfill of stored rows
  Given mentions of copies stored before this change
  When  the backfill runs
  Then  the canonicals of those copies show the events, and a second run changes nothing
  Verify: auto

AC-4  `mention_count` unchanged
  Given an event with 3 real mention rows, one of them naming a copy
  When  the canonical is read with `include=events`
  Then  that event's `mention_count` is 3
  Verify: auto

AC-5  No duplicate event
  Given the canonical and a copy are both mentioned in the same event
  When  the canonical is read with `include=events`
  Then  the event appears once
  Verify: auto

AC-6  Cap and order kept
  Given a canonical whose own and copies' events exceed `api.events_per_article`
  When  it is read with `include=events`
  Then  at most the cap are returned, most mentioned first, ties by `event_id`
  Verify: auto

AC-7  Replay is idempotent
  Given the same Mentions message is processed twice
  When  the sink handles both
  Then  the canonical's events and counts are the same as after one run
  Verify: auto

AC-8  Retention covers derived rows
  Given derived links whose mentions are older than `retention_days`
  When  retention runs
  Then  they are deleted with those mentions
  Verify: auto

AC-9  Same through MCP and REST
  Given the canonical of AC-1
  When  it is read with `get_article`, `GET /api/articles/{id}`, and `include=events` on a list or search
  Then  all carry the copy's event
  Verify: auto

AC-10  Payload unchanged elsewhere
  Given the same canonical
  When  a list or search runs without `include`, or an article with no events is read with `include=events`
  Then  there is no `events` key, respectively `events` is `[]`
  Verify: auto

## 7. Non-functional requirements

Provisional targets (measure first): sink time per mentions batch and `include=events` page time do not grow noticeably; storage growth measured on a real slot.

## 8. Assumptions

Grouping order is arbitrary (§3); 7-day retention unchanged; one sink and one API worker.

## Glossary

- **Canonical article:** the one row of a story in `articles`. **Copy:** another page of the same story in `article_sources`.
- **Derived link:** a stored row that makes a copy's mention visible on the canonical.
- **`mention_count`:** stored mention rows of an event (ADR-0033).
