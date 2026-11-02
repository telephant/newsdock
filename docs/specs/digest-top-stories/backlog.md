# digest-top-stories — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Rolling window for ranking (P1, from risk 1):** each cycle reads the last 24 hours with `search_articles` (about 80 calls of 100) so `source_count` is current and the Top block means "what the world is on about today"; stateless, no cursor. Recommended at spec time and not chosen (D-6); revisit after a day of digests shows whether late-growing stories are missed.
- **Platform `domain_count` in the article summary (P1, from the T-01 spike):** the number of distinct domains among a story's copies, so syndication networks stop inflating coverage; the proper fix for risk 3. Optional agent-side fallback (P2): re-rank the ~30 best candidates by distinct domains with `get_article`.
- **Platform story clustering (P1):** replace the lexical grouper through the `StoryGrouper` port with the platform's embedding-based clustering once it exists (an MCP tool that returns neighbours or groups).
- **Platform top-stories tool or `min_sources` filter (P2):** let the platform return widely covered stories directly, so the agent does not page the whole window.
- **Wire and press-release blocklist (P3):** measured at 0.9% of articles on 2026-11-02, so low impact; the minimum-coverage rule already keeps single-source items out.
- **Region sections (P2):** needs a region signal; 74% of domains have no country hint, so it needs platform support (locations from GKG) or a model.
- **Model-chosen section label (P3):** only if the theme-prefix map proves too coarse.
- **Readable labels for unmapped themes (P3):** the old backlog item, still relevant for "Other".
- **Digest page in the web UI (P2):** needs somewhere to store digests (a table or an endpoint).
- **Daily roll-up (P3):** a once-a-day digest built from the day's hourly files.
- **Event-driven wake-up (P3):** use the SSE stream instead of sleeping an hour.
- **CI job for `agents/whathappen` (P2, carried over):** path-filtered, runs `make -C agents/whathappen check`.
