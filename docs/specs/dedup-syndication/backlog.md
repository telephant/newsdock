# dedup-syndication — Backlog (after Milestone 2a)

- **Canonical-quality selection (P2):** prefer the originating outlet over syndicates as the canonical (e.g. domain ranking, earliest precise timestamp). Why: "first copy wins" may crown a small syndicate.
- **Fuzzy/semantic grouping (P2, M3 tie-in):** group reworded duplicates via pgvector embeddings; normalized title misses rewrites. Builds on the M3 semantic-search milestone.
- **Regroup/backfill job (P3):** re-key existing rows after a normalization change; M2a relies on 7-day retention instead (D-4).
- **Merge repair (P3):** when a late copy reveals that two canonicals are one story (or a false merge is found), merge/split with analyses carried over.
- **Cross-language story grouping (P3, M6):** same story via the translation feed.

## Follow-ups from /spec-verify (2026-10-09)

- **Same-page detection for URL variants with different ids (P3, M3 tie-in):** rttnews (`story.aspx?Id=` vs `/<id>/slug.aspx`) and israelnationalnews (`/news/<id>` vs `/flashes/<id>`) copies stay separate after the D-6 guard. Harmless duplicates; revisit with fuzzy matching.
- **Generic titles across different domains (P3):** not guarded; none seen in the 4,110-copy sample.
- **"Seen on N sites" counts copies, not distinct domains (P3):** 19 iHeart stations read as 19 sites.
- **Agent-call reduction from a real LLM run (P3):** measured from the store (25.6 % fewer), not from a live `llama3.2:3b` batch.
