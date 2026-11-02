# digest-top-stories — Tests

Derived from the ACs in [spec.md](spec.md) §7 and the design in [design.md](design.md). Every AC has at least one test and every test names its AC. All tests are in `agents/whathappen/tests/` (pytest, `--import-mode=importlib`: helpers are fixtures, not imported modules) and run with `make -C agents/whathappen test`.

## 1. Test data and where it lives

- **Real headlines** (committed under `agents/whathappen/tests/fixtures/`, exported once by T-01 from the dev database, read-only; titles, domains and URLs of public news, like the existing `digest_window.json`):
  - `story_window.json`: one real hourly window of new articles, as `list_new_articles` returns them (about 2 000 rows, with `source_count`, `themes`, `tone_neg`), used by the cycle, performance and golden tests.
  - `story_pairs.json`: labelled headline pairs from the 24 h data, each `{a, b, same: true|false, why}`. Seeded with the pairs decided in the spec: the Murphy stroke rewordings (same), the Stevens/Rogers endorsement rewordings (same), the Florida jet crash (same), "Senator Chris Murphy Hospitalized After Stroke" against "Sullivan Accuses Peltola Of Voter Confusion Tactics" (different), the Alaska ruling against the Peltola story (different), two unrelated "…announces…" headlines (different), and nine "Field Level Media Top 25: No. N Team" headlines from one domain (all different).
  - `digest_golden.md`: the exact markdown expected for a small hand-picked window (TC-19).
- **Hand-made cases** for edge conditions (ties, a missing tone, equal scores, hostile text, a window of single-source articles) are built in the tests with the existing `make_article` fixture, extended with `tone_neg`.
- **Fakes** for the platform (`FakeMcp`, scripted pages), the model (`FakeSummariser`, can fail) and the file sink (`FakeSink`, can fail) follow the pattern of the existing `test_cycle.py`; the real `McpClient` and `OllamaSummariser` are tested with fake transports as before.
- No test reads a real `.env`, the network, Ollama or the platform; the live run is manual (TC-20).

## 2. Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | **Given** groups of (sources, tone_neg) (50, 2.0), (35, 6.7), (60, 0.2) **When** scored with divisor 10 **Then** the scores are 60.0, 58.45, 61.2 and the order is (60, 0.2), (50, 2.0), (35, 6.7); ties on score break by sources, then newest, then id; the divisor is a setting |
| TC-2 | AC-2 | unit | **Given** groups whose articles have no `tone_neg` key, or only null values **When** scored **Then** each score equals its source total, `ranking` is `"coverage"`, and with one non-null value it is `"coverage and tone"`; a missing tone counts as 0 inside a group that has some |
| TC-3 | AC-3 | unit | **Given** the real Murphy, Stevens and jet pairs from `story_pairs.json` (published within the window) **When** `LexicalGrouper.group` runs **Then** each pair is one group with the summed source total, the shown headline is the one with more sources (ties: newest) and the other is listed as "Also" |
| TC-4 | AC-4 | unit | **Given** the pairs marked `same: false` and the nine same-domain "Field Level Media Top 25" headlines **When** the grouper runs **Then** every one of them is its own group (the same-domain guard keeps the template headlines apart) |
| TC-5 | AC-5 | unit | **Given** a matching pair published 47 h 59 min apart, one 48 h 01 min apart, and the window set to 24 h **When** the grouper runs **Then** the first merges, the second does not, and the 24 h setting splits the first |
| TC-6 | AC-3, AC-4 | unit | **Given** `title_tokens` and the match rule **When** fed entities, stop-words, plurals, long words, numbers a title of fewer than 3 significant words and titles ending in ` | Outlet` **Then** trailing ` | Outlet` segments are removed from the shown and the tokenised title (a second one only while 3+ words remain; a title that is only a segment is left alone); tokens are lowercase sets with stop-words dropped, plurals folded and words over 6 characters truncated to 6; the rule merges at overlap 0.75 / Jaccard 0.5 with at least 3 shared words, and not at 0.74 / 0.49 or with 2 shared words |
| TC-7 | AC-6 | unit | **Given** 8 scored groups of several sources **When** selection and rendering run **Then** the Top stories block holds exactly the 5 highest scores in descending order, each line a link with its source total, and none of them appears again in a section; fewer than 5 qualifying groups gives a shorter block |
| TC-8 | AC-7 | unit | **Given** groups whose articles' themes hit the prefixes of "Politics & Government" and "Conflict & Security" (one group with hits for both, the second label ahead), a tied group, and a group with no match **When** sections are assigned **Then** each group takes the label with most theme hits across its articles, the tie goes to the label listed first, the unmatched group to "Other", sections are ordered by best score, an empty section is omitted, a label needs at least `section_min_hits` hits (2 sends a one-hit group to Other), and the caps (`max_sections`, `groups_per_section`) hold |
| TC-9 | AC-7, AC-13 | unit | **Given** `Settings` **When** `section_labels` is set from a JSON environment value, left unset, or set to invalid JSON **Then** the value is used, the default map applies, `section_min_hits` defaults to 1, and invalid JSON fails at start with a clear message; the heartbeat age uses the new group counts |
| TC-10 | AC-8 | unit | **Given** a window whose groups all have one source, and another with some groups of 2 or more **When** a cycle runs **Then** the first writes a file with the heading, the notice and "No story was carried by 2 or more outlets this hour.", acks the cursor, and calls the model zero times; in the second only groups at or above `min_group_sources` are listed |
| TC-11 | AC-9 | unit | **Given** one single-headline group and one group with three distinct headlines **When** the cycle builds the digest **Then** the summariser is called once with exactly those three titles (no counts, urls, labels or other groups), the single group shows its headline with no model line, and the prompt text is pinned |
| TC-12 | AC-10 | unit | **Given** a summariser that raises for one group and returns `None` for another **When** the cycle runs **Then** those groups show their links and no model line, the others keep theirs, the file is written and the cursor acked |
| TC-13 | AC-11 | unit | **Given** headlines, domains and URLs with markdown, HTML, entities, control characters and instructions **When** rendered in the Top block and in a section and read with the stdlib link reader **Then** each is one well-formed link or plain text and nothing is interpreted as markup |
| TC-14 | AC-12 | unit | **Given** a window ending at cursor C **When** the file is written successfully and when the write fails **Then** the recorded order is `list…`, `write`, `ack:C` with exactly one ack; on `OSError` there is no ack and the next cycle re-reads the same window |
| TC-15 | AC-2, AC-12 | unit | **Given** a scripted platform of 3 pages (200, 200, 37) **When** a cycle runs **Then** every page is used in order, every `list_new_articles` call carries `include=["tone_neg"]` (the real `McpClient` sends it as an argument), an empty window writes and acks nothing, and an article dict without `tone_neg` still parses |
| TC-16 | AC-13 | unit | **Given** the agent folder **When** the source, tests, README, Makefile, compose and `.env.example` are searched and `Settings` inspected **Then** there is no `themes`, `baseline` or `stories` module, no field named `skip_theme_prefixes`, `min_theme_count`, `max_themes`, `stories_per_theme`, `prompt_titles`, `baseline_*` or `state_file`, no text "vs usual" or "no baseline yet", and a `.env` that still contains the removed names starts without error |
| TC-17 | AC-14 | unit | **Given** an output folder with two old dated digests (no marker), an old `latest.md`, `baseline.json`, a new dated digest and a new `latest.md` (marker first) **When** `clean-old --dry-run` runs, then `clean-old` **Then** the dry run prints exactly the old files and deletes nothing; the real run deletes exactly them and the emptied date folders, and the new files remain byte-identical |
| TC-18 | AC-14 | unit | **Given** unknown files, a symlink inside `output_dir` pointing outside it, a missing folder and an empty folder **When** `clean-old` runs **Then** unknown files are kept and listed, nothing outside `output_dir` is touched or followed, a missing or empty folder is a clean no-op with exit 0, and the loop never calls the cleanup |
| TC-19 | AC-6, AC-7, AC-11 | unit | **Given** the hand-picked window of the golden fixture **When** the full cycle runs with a fake model **Then** the file equals `digest_golden.md` byte for byte (marker, heading, notice, Top stories, sections, "Also" lines) |
| TC-20 | AC-15 | manual | See the checklist below |

**Regression updates (not new ACs):** `test_cycle.py`, `test_render.py`, `test_prompt.py`, `test_config.py`, `test_loop.py` and `test_mcp.py` are rewritten or adjusted for the new shapes in the tasks that change their subjects; `test_themes.py`, `test_baseline.py`, `test_stories.py` and the baseline part of `test_files.py` are deleted with their modules (T-07). `test_summarise.py`, `test_heartbeat.py` and `test_packaging.py` (independence from the platform) stay and must keep passing.

## 3. Manual checklist (TC-20, AC-15)

Run by the owner (or by me with the owner's key), with the platform up and Ollama running:

1. For tone ranking: the platform API is rebuilt from the `tone-in-summary` code (otherwise skip the tone items and expect "Ranked by outlets covering a story").
2. `make -C agents/whathappen once` exits 0 and prints the digest; `output/latest.md` and the dated file exist and are identical.
3. The first line is the marker; the heading counts look right; the notice names the ranking used.
4. The Top stories block shows real headlines with working links; open at least five links (one from each section) in a browser.
5. The same event does not appear twice in the Top block (compare the headlines).
6. Sections carry plain labels (no theme codes), no empty section is shown, "Other" is not the biggest section.
7. A group with several headlines has one model sentence that matches its headlines; single-headline groups have none.
8. Read it against the previous theme digest: is it clearer? (the owner's call, recorded in verify.md).
9. Run `make -C agents/whathappen clean-old` as a dry run; it lists only old files.

**Result (2026-11-02, the owner):** ran end to end on the live platform; the summaries and the categories were judged bad. Recorded as known limitations in [verify.md](verify.md) (F-8).

## 4. Measurements (provisional targets: measure first, no pass/fail)

| ID | What | How |
|---|---|---|
| M-1 | Grouping time on a real hour | Time `LexicalGrouper.group` on `story_window.json` (about 2 000 titles); record seconds and the number of comparisons |
| M-2 | How full the digest is | On 3 or more real hourly windows record groups with 2 or more sources, Top block fill, sections used, share of groups in "Other" |
| M-3 | Merge quality | On `story_pairs.json` plus a hand-checked sample of 20 merged groups from a real day: false merges and missed merges; re-tune `match_*` if needed |
| M-4 | Cycle time end to end | `make once` on a real hour with Ollama: total seconds and number of model calls (at most `top_stories + max_sections × groups_per_section`) |
| M-5 | Late-growing stories (risk 1) | For one real day, compare each Top story's `source_count` as seen at its own hour with its count a day later; record how many of the final top 10 were missed or ranked low |
