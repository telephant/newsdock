# what-happen — Tests

Every `AC-n` in [spec.md](spec.md) is covered below. Tests are written before the code they check (see [plan.md](plan.md)). Unit tests live in `agents/whathappen/tests/unit/` and run with `make -C agents/whathappen test`; they need no Docker, network or Ollama.

## 1. Test data

| Data | Where | Notes |
|---|---|---|
| Hand-made articles (title, url, domain, published_at, themes, source_count, article_id) | built by `make_article(...)` in `agents/whathappen/tests/conftest.py` | no fixture files needed; edge titles included (brackets, newline, pipe, backtick) |
| A real sample of one live window | `agents/whathappen/tests/fixtures/digest_window.json` (30 real articles, captured in T-01, done) | used by one smoke test (TC-13) and the manual check |
| Fake MCP | `FakeMcp` in `test_cycle.py`: scripted pages, records calls in order | implements `list_new_articles(limit, cursor)` and `ack_cursor` |
| Fake summariser | `FakeSummariser` in `test_cycle.py`: per-theme text or exception | |
| Fake Ollama HTTP | `httpx.MockTransport` in the adapter test | same technique as `test_ollama.py` |
| Fake clock and sleep | `FakeClock` in `agents/whathappen/tests/conftest.py` (fixture) | no real waiting in any test |
| Real filesystem | pytest `tmp_path` | read-only directory via `chmod` for TC-5 |

## 2. Cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given a FakeMcp with 3 pages (200, 200, 37 articles) and `batch_limit` 200, when a cycle runs, then all 437 articles are counted in order and exactly 3 `list_new_articles` calls are made (the first without a cursor, the next two with the previous `next_cursor`) |
| TC-2 | AC-1 | unit | Given `max_articles` 300 and pages of 200, when a cycle runs, then paging stops after the page that reaches the cap, the digest covers those articles, and the ack is the cursor of the last page read |
| TC-3 | AC-1 | unit | Given the real `McpApiClient` with a stubbed `_call`, when `list_new_articles(limit=200)` and `list_new_articles(limit=200, cursor="c")` run, then the first sends only `limit` and the second sends `limit` and `cursor` |
| TC-4 | AC-2 | unit | Given a successful window ending at cursor C, when the cycle finishes, then the recorded call order is `list…, write file, ack_cursor(C), save baseline`, `ack_cursor` is called once, and the file exists and is complete at that moment |
| TC-5 | AC-3 | unit | Given a digest directory that cannot be written (read-only), when a cycle runs, then `ack_cursor` is never called and the baseline is unchanged; and when the directory is writable again and the same FakeMcp window is served again, the digest is written and acked |
| TC-6 | AC-4 | unit | Given a baseline of 3 hours where theme A averaged 10 and B 60, and a window of the usual size with A=40, B=60, when themes are ranked, then A is first (rise 4.0) and B second (rise 1.0) |
| TC-7 | AC-4 | unit | Given themes with a skip prefix, a count under the minimum, and more themes than `max_themes`, when ranked, then skipped and under-minimum themes are absent and the list is cut to the maximum; a theme never seen in the baseline gets rise = its count (expected floored at 1); a window twice the usual size does not double every rise |
| TC-8 | AC-5 | unit | Given 2 baseline entries (under the minimum of 3), when ranked, then order is by plain count, rise is `None`, and the rendered section line says "no baseline yet" |
| TC-9 | AC-5 | unit | Given a baseline file that is missing / empty / not JSON / wrong `version` / entries of the wrong shape (parametrized), when the store loads it, then it returns an empty baseline without raising and a cycle completes |
| TC-10 | AC-6 | unit | Given a theme with 10 stories (ties in `source_count`), when picked with K=3, then the 3 shown are the highest `source_count`, ties by newest `published_at` then `article_id`; a story carrying two ranked themes is listed only under the higher-ranked one while the lower theme takes the next best; and each theme returns up to `prompt_titles` own stories for the prompt, none shared with an earlier theme |
| TC-11 | AC-7 | unit | Given titles containing `[`, `]`, `\`, `*`, `_`, a backtick, `<`, `>`, `|`, a newline and HTML entities such as `&#x2013;` (decoded once, so the dash appears, not the entity), and a URL with `)` and a space, when the story line is rendered, then it is one line and a small test parser recovers the cleaned title and the exact original URL |
| TC-12 | AC-7 | unit | Given `source_count` 1 and 14, and a `None` domain, when rendered, then the line reads "1 source" / "14 sources" and omits the domain part cleanly; an empty-after-cleaning title renders as the URL |
| TC-13 | AC-8 | unit | Given a cycle with 3 themes (and, separately, the real sample `digest_window.json`), when rendered, then the text has exactly one `#` heading with date, hour, article count and "since" time (or "first run"), then the notice line, then one `##` section per theme in rank order, each with its summary line and its story lines, and no other content |
| TC-14 | AC-9 | unit | Given a theme with titles and a window containing other themes' titles, counts and URLs, when the prompt is built, then it contains the theme label and only that theme's titles (at most `prompt_titles`), and none of: a count, a URL, another theme's title |
| TC-15 | AC-10 | unit | Given a FakeSummariser that raises for one theme, when a cycle runs, then that section reads "Summary unavailable." with its links, other sections keep their sentences, and the file is written and acked |
| TC-16 | AC-10 | unit | Given an Ollama MockTransport returning (a) a normal sentence, (b) a multi-line answer with list markers and quotes, (c) an over-long line, (d) an empty answer, (e) HTTP 500, (f) a timeout, when summarised, then (a)–(c) give a cleaned single line within `summary_max_chars` and (d)–(f) give `None` without raising |
| TC-17 | AC-11 | unit | Given a FakeMcp whose first page is empty, when a cycle runs, then no file and no `latest.md` exist, `ack_cursor` is not called, the baseline is unchanged, and an INFO line says the window was empty |
| TC-18 | AC-12 | unit | Given a cycle at 2026-10-30 14:07 UTC, when written, then `<dir>/2026-10-30/1407.md` and `<dir>/latest.md` have identical text, no temp file remains, and a simulated failure between temp write and rename leaves the previous `latest.md` intact |
| TC-19 | AC-13 | unit | Given the loop with FakeClock, interval 3600 and a cycle that fails on the 2nd run, when 3 hours are simulated, then there are cycles at t=0, 1h, 2h (3 runs), the failure is logged and does not stop the loop, the heartbeat is written after each pass, and `--once` runs exactly one cycle |
| TC-20 | AC-14 | unit | Given a stored baseline of 24 entries, when a cycle appends one, then 24 entries remain (oldest dropped), each entry keeps at most `baseline_themes_kept` themes with count ≥ 2, and the save goes through temp file and rename |
| TC-21 | AC-15 | unit | Given `Settings`, then no field name mentions a database, Kafka or DSN, the variables use the `WHATHAPPEN_` prefix (the platform's `NEWSDOCK_AGENT_` is ignored), the agent's own `.env` is read and the environment wins over it, the key never appears in a repr, and the defaults equal design-detail §1 (`test_config.py`) |
| TC-22 | AC-15 | unit | Given the agent's folder, when parsed, then no source or test file imports `newsdock*`, `apps` or `packages`; `pyproject.toml` depends on no workspace package; `compose.yaml` declares no network and no `depends_on`, has no database or Kafka env, takes the key from the optional `.env` and never inline, reaches the host as `api` and `host.docker.internal`; `.env` and `output/` are git-ignored; the Dockerfile needs only its own folder (`test_packaging.py`) |
| TC-23 | AC-15 | manual (live, done 2026-10-30) | Given the container started with `docker compose up -d --wait` in `agents/whathappen`, then it is healthy, runs as uid 1000, is attached to its own `whathappen_default` network only, and reaches the platform's MCP through the `api` alias (no Docker scene needed: it shares no network with the platform) |
| TC-24 | AC-16 | manual | The checklist in §4 |

## 3. Coverage

Every AC-1…AC-16 has at least one TC; every TC names an AC. Security-flavoured cases: TC-11 and TC-12 (markdown injection), TC-14 (nothing else leaks into the prompt), TC-21 and TC-22 (no data route but MCP, key separation).

## 4. Manual checklist (TC-24, AC-16)

Needs the dev stack running with a few hours of articles, Ollama running with the chosen model, an agent made with `make agent-create NAME=<digest agent>` and its key in `.env` as `WHATHAPPEN_API_KEY`.

Run 2026-10-30 against the live dev stack (1 932 articles in the first-run window). Differences from the written steps: this worktree has no `.env`, so I ran the same entry point (`python -m whathappen --once`) with a throwaway agent's key instead of `make once`, wrote to `agents/whathappen/output/`, and later removed those sample files.

- [x] The digest cycle exits 0 and prints the digest (6 s for paging, 8 summaries, and writing). The `make once` wrapper itself was not run (no `.env` here); it only sets the key and `MCP_URL` and calls the same module.
- [x] `<output_dir>/2026-10-30/1148.md` and `latest.md` exist and are identical (`cmp`).
- [x] The first line says the date, hour, article count and "first run"; 8 sections of one sentence and 3 links is about 40 lines, a little over one screen.
- [~] Five random links, checked by script: all five are real hosts and plausible article URLs; 1 loaded and its page contained the headline words, 2 answered 451 (regional block) and 2 answered 403 (bot block) to a script. **Owner: open five links in a browser to close this item.**
- [x] Summaries, judged on three sections: with `prompt_titles` 8 the sentence described stories the reader could not see (unverifiable, and a mash of unrelated items), so the default is now 3; with 3 every sentence matches its three links, reruns at temperature 0 are identical, and nothing is invented. They are accurate enumerations of loosely related stories, not insight (spike §2.5).
- [x] Immediate second run: the window was empty, nothing was written, `latest.md` was unchanged.
- [x] The `digest` compose service (`up -d --no-deps --build digest`, so the running stack was not touched): healthy after 6 s, wrote a digest at start, `latest.md` appeared on the host, the baseline was written to `/data`. Container and volume were removed afterwards.
- [~] Ollama down: simulated with an unreachable `OLLAMA_URL` (the owner's Ollama was not stopped): all 8 sections showed "Summary unavailable." with their 3 links and the digest was written in 0.3 s. "The cursor still moves" is covered by TC-15 (unit); the live run used an ack-less script for this case.
- [ ] The demo agent still scores with its own key and cursor: not exercised (its container was not recreated or restarted).

## 5. Measurements (T-01 and T-11, 2026-10-30)

| What | Result |
|---|---|
| Articles per hour on the live stack | 1 932 to 2 562 in the first-run window; 10 to 13 pages; 0.5 s to page |
| Cycle duration with `qwen3:4b-instruct` | about 3 s of model time for 8 themes; 6 s end to end on the host (cold model load included); budget of 10 minutes is far away |
| Share of themes that are generic (top 40 by count) | most of them; `skip_theme_prefixes` filled in T-01 |
| `digest-baseline.json` size | 6.4 KB for one entry (skip-listed themes are not stored), so about 150 KB for 24 entries, far below the 2 MB first estimate |
| Summary quality: model A vs model B | `qwen3:4b-instruct` chosen in T-01; prompt titles 8 vs 3 compared in T-11, 3 chosen |
| Rise factors of the top 8 after a day | **not measured**: needs at least 3 stored cycles (the service has to run for hours); first look belongs to `/spec-verify` or the owner |
