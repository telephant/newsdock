# what-happen — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Body-based summaries (P1, needs M3 body extraction):** the digest summarises headlines only; with article text the summaries become worth reading on their own.
- **Group by story similarity, not by theme (P1 for digest quality, from the T-01 spike):** GDELT themes group unrelated headlines at hour scale; clustering by title embeddings (already in Postgres) would give coherent groups. Needs an MCP tool that exposes neighbours or vectors.
- **Fix `published_at` outliers (P2, from the T-01 spike):** at least one article in a live window was dated 2004; check the processor/sink date handling.
- **Digest page in the web UI (P2):** list and open the hourly digests; needs somewhere to store them (a table or an endpoint), since the agent has no database access.
- **Readable theme labels (P2):** a proper name per GDELT theme code (today: the code with underscores turned into spaces).
- **Region / theme filter (P2):** `digest_theme_prefixes` to cover only `ECON_*` or one country.
- **Daily roll-up (P3):** a once-a-day digest built from the day's hourly files.
- **Model comparison in the eval (P3):** score summaries against hand-labelled hours; today the model is judged by reading.
- **Event-driven wake-up (P3):** use the SSE stream instead of sleeping an hour; only if an hourly cadence feels stale.

## Follow-ups from /spec-verify (2026-10-30, see verify.md)

- **F-1 (P1) Browser link check:** open five links from a digest; four of five sites answered a script with 451/403. Closes AC-16.
- **F-2 (P2) Run the Docker isolation scene (TC-23):** `make down`, then `make test-infra SCENE=e2e`.
- **F-3 (P1) Warm-baseline look:** run the `digest` service for a day and read `infra/digests/`; if rising themes still group unrelated stories, build the "group by story similarity" item above.
- **F-4 (P2) Demo agent after the image rebuild:** confirm it still scores (its container was not recreated).
- **F-5 (P3) Housekeeping:** disable the throwaway agents `whathappen-spike` and `whathappen-spike2` in the UI; create `whathappen` with `make agent-create` and put its key in `.env`.
