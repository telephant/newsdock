# digest-top-stories — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Rolling window for ranking (P1, from risk 1):** each cycle reads the last 24 hours with `search_articles` (about 80 calls of 100) so `source_count` is current and the Top block means "what the world is on about today"; stateless, no cursor. Recommended at spec time and not chosen (D-6); revisit after a day of digests shows whether late-growing stories are missed.
- **Platform `domain_count` in the article summary (P1, from the T-01 spike):** the number of distinct domains among a story's copies, so syndication networks stop inflating coverage; the proper fix for risk 3. Optional agent-side fallback (P2): re-rank the ~30 best candidates by distinct domains with `get_article`.
- **Platform story clustering (P1):** replace the lexical grouper through the `StoryGrouper` port with the platform's embedding-based clustering once it exists (an MCP tool that returns neighbours or groups).
- **Platform top-stories tool or `min_sources` filter (P2):** let the platform return widely covered stories directly, so the agent does not page the whole window.
- **Wire and press-release filter (P3):** measured 0.9% of articles by domain pattern and 1.3% of URLs by path on 2026-11-02; in the 08:00 hour 4 of 28 listed stories were press releases, none in a Top 5. A URL-path match (`/press-releases/`, `newswire`) is the better handle than the domain.
- **Region sections (P2):** needs a region signal; 74% of domains have no country hint, so it needs platform support (locations from GKG) or a model.
- **Model-chosen section label (P3):** only if the theme-prefix map proves too coarse. Try `WHATHAPPEN_SECTION_MIN_HITS=2` first (verify F-4).
- **Summary and category quality (P3, verify F-8):** the owner's live read (2026-11-02) judged both bad; a demo, so it may not be revisited. First tries: `WHATHAPPEN_SECTION_MIN_HITS=2`, a larger model or stricter prompt, a model-chosen label, or headlines only without sentences.
- **Readable labels for unmapped themes (P3):** the old backlog item, still relevant for "Other".
- **Digest page in the web UI (P2):** needs somewhere to store digests (a table or an endpoint).
- **Daily roll-up (P3):** a once-a-day digest built from the day's hourly files.
- **Event-driven wake-up (P3):** use the SSE stream instead of sleeping an hour.
- **CI job for `agents/whathappen` (P2, carried over):** path-filtered, runs `make -C agents/whathappen check`.
