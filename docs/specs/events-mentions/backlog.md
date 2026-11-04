# Backlog — events-mentions

Later items, one line each (P1 highest).

- **Digest uses mention counts (P2):** replace the lexical `sources` count in the `whathappen` story ranking with the platform's mention outlets per article. Why: GDELT's own count is more reliable than title matching. Deferred by D-3.
- **Event search filters (P2):** filter articles by CAMEO root code, actor country or Goldstein range in `search_articles`, `list_new_articles` and saved subscriptions. Why: lets an agent ask for "protests in France" without text matching.
- **Push on events (P3):** wake SSE streams when an event of a given type appears. Why: push-delivery covers articles only.
- **Remaining Events columns (P3):** actor 2 geography, actor ethnic/religious/known-group codes, ADM1/ADM2 codes, `DATEADDED` and the actor-level geography. Why: stored only if an agent needs them (D-2 keeps a curated subset).
- **Mention detail fields (P3):** expose per-mention confidence, in-text position and tone, not only the count. Why: only the count is served in this milestone.
- **Done 2026-11-04 as M3e `events-grouped-copies` (ADR-0038), kept for the record. Events through grouped copies (P2, verify F-1):** also return the events of the copies of a story (join `mentions.url_hash` through `article_sources.url_hash` to the canonical). Why: only the canonical is in `articles`, so 26 of 996 events and 727 of 2,514 mentions in a sample slot do not show on any article; 5 of 778 canonicals would gain an event.
- **Trim the mentions table (P3, verify F-2):** if the 7-day size read from a live stack is too large (estimate 0.35–1.1 GB), drop `mentions.url` (it can be read from `articles`/`article_sources`) or the `ingested_at` index. Why: the first size guess was low.
- **Events with no article in our store:** closed by measurement, every event and mention URL in a real slot is stored as a canonical or a copy (0 of 996 and 0 of 2,514 missing).
- **Event-centred views in the web UI (P3):** an events screen and an article page block. Why: this milestone serves agents only.
- **Body extraction (P2):** the other half of M3; its own spec (`/spec-init body-extraction`).
