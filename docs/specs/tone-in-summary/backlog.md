# tone-in-summary — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Live check once the dev stack runs this code (P2, verify F-1):** after merge, rebuild only the `api` image and recreate only that service (see verify.md F-1; `make up` does not start apps), then call `search_articles(min_negativity=8, include=["tone_neg"])` with a real key. No migration.
- **Use tone in the whathappen digest (P1):** a "Worrying now" top-5 block ranked by coverage and `tone_neg` (`agents/whathappen`, its own spec; see the digest quality notes in `docs/specs/what-happen/backlog.md`). Needs this spec shipped first.
- **Tone badge / filter in the web UI (P2):** show `tone` on the feed and detail, and a negativity control on the feed.
- **Sort by negativity (P2):** `order=negativity` on search and the REST feed, if a consumer cannot rank client-side.
- **Index on `tone_neg` (P2):** only if the measured latency of `min_negativity` needs it (spec §7).
- **`min_negativity` on `list_new_articles` (P3):** a filter on a cursor feed needs a decision on what the cursor skips.
- **`include` on subscription streams and the live feed (P3):** payload for SSE consumers.
- **Other tone filters (P3):** `max_tone`, `min_polarity`, a positive-tone filter.
- **`word_count` in lists (P3):** useful to drop very short items.
