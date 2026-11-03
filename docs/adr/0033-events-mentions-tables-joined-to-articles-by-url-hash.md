# ADR-0033: Events and Mentions tables, joined to articles by url_hash through mentions

Status: **Accepted 2026-11-02** (spec `events-mentions`, D-2, D-5; confirmed by the user during `/spec-design`)

## Context
An event has an id and one `SOURCEURL`; a mention links an event id to a URL. In the sample slot every event's own `SOURCEURL` is also among its mentions (996 of 996), mentions repeat an (event, URL) pair inside one slot (53 of 2,567 rows), and 42% of mentioned events come from earlier slots (spec §3). Files of a slot arrive in any order. Article ids are `url_hash` (sha256 of the normalised URL). The user decided: no foreign key, curated columns (D-2, D-5).

## Options
- **(a) `events` PK `event_id`, `mentions` PK `(event_id, url_hash)`, no FK; an article's events are found through `mentions.url_hash`.** One join covers "reported by" and "mentioned in".
- **(b) Join events to articles by `events.source_url_hash` only.** Simplest, but ignores mentions entirely and the mention count.
- **(c) Aggregate mentions into a count column on events and store no mention rows.** Smallest storage, loses which article mentions which event.
- **(d) Foreign keys from both tables to `articles`.** Rejected in D-5.

## Decision
**(a)**. Events upsert by `event_id` (newer `date_added` wins); mentions upsert by `(event_id, url_hash)`; batches are deduplicated in memory before the statement. Retention deletes by `ingested_at` in both tables. The API returns, per article, the events found through `mentions.url_hash = :article_hash`, at most `api.events_per_article` (20), by `num_mentions` descending, each with `mention_count` (rows in `mentions` for the event). `events` is a new name for `include` (ADR-0030 pattern), always on in the detail.

## Consequences
+ Tolerates late and out-of-order rows; replays are harmless.
+ One indexed join; the same data later supports "which articles cover this event".
− About 1.3–2.0 M mention rows in 7 days (measured on 7 real slots, spec-verify 2026-11-02), 0.35–1.1 GB with indexes; the join adds about 2 ms to a page of 50 articles (3.4 ms plain, 5.4–6.3 ms with `events`).
− Added at verify (2026-11-02): only the canonical article of a story is in `articles`, so events and mentions whose URL is a grouped copy (`article_sources`) do not appear on the canonical article. In the sample slot that is 26 of 996 events and 727 of 2,514 mentions, but only 5 of 778 canonical articles would gain an event through their copies (`docs/specs/events-mentions/verify.md` F-1, backlog).
− Orphans exist (mentions of events we never stored); they expire with retention and are hidden by the inner join.
− `mention_count` counts the mentions we stored, not GDELT's `NumMentions` (both are returned and can differ).
− The meaning "events a page is mentioned in" is broader than "events it reports"; it is documented in the tool description.
