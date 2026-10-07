# dedup-syndication — Backlog (after Milestone 2a)

- **Canonical-quality selection (P2):** prefer the originating outlet over syndicates as the canonical (e.g. domain ranking, earliest precise timestamp). Why: "first copy wins" may crown a small syndicate.
- **Fuzzy/semantic grouping (P2, M3 tie-in):** group reworded duplicates via pgvector embeddings; normalized title misses rewrites. Builds on the M3 semantic-search milestone.
- **Regroup/backfill job (P3):** re-key existing rows after a normalization change; M2a relies on 7-day retention instead (D-4).
- **Merge repair (P3):** when a late copy reveals that two canonicals are one story (or a false merge is found), merge/split with analyses carried over.
- **Cross-language story grouping (P3, M6):** same story via the translation feed.
