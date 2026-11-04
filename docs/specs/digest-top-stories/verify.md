# digest-top-stories — Verify

Verified 2026-11-02 on branch `agents-whathappen`, worktree `p2-delivery` (committed through T-06; T-07 to T-09 are in the working copy). **Verdict: pass with follow-ups.** All 14 automatic ACs hold with their named tests passing in this run. AC-15, the owner's read of a real hour on the live platform, was done on 2026-11-02: it **ran end to end, but the owner judged the summaries and the categories bad** (see "Owner's live read"). That is recorded as a known limitation, not fixed: the agent is a demo and may not be revisited. The mechanics were also run on real data with the real model (below), and that run showed what the spike predicted: the pipeline is sound and the ranking is only as good as outlet coverage.

## What was run in this session

| Run | Result |
|---|---|
| `make -C agents/whathappen check` (ruff, ruff format, mypy strict, pytest) | exit 0; **210 passed** (16 test files) |
| Root `make check` (ruff, mypy, import-linter, layout rule for `agents/`, config, 763 Python tests, 182 web tests, docs check) | exit 0 |
| Spike measurements on three real hours (07, 08, 09 UTC, 5 044 articles) with the production code and default settings | below (M-1 to M-5) |
| One real cycle: the real hour fixture (1 613 articles) through the real grouper, scoring, selection and renderer, with the real model `qwen3:4b-instruct` on this machine, over a fake MCP | 4.4 s, 8 model calls, 0 empty answers, files written as `2026-11-02/0905.md` and `latest.md` |
| Cleanup on the owner's real output folder: dry run, then `clean-old-yes` | listed exactly `2026-10-30/1351.md`, `latest.md`, `baseline.json`; deleted 3 files and 1 empty date folder; the folder is now empty |

Not run: a cycle against the live platform (needs the owner's key; AC-15), and the Docker container for the agent.

## Results per acceptance criterion

| AC | Tests | Result | Evidence |
|---|---|---|---|
| AC-1 score ranks coverage and tone | TC-1 | pass | `test_scoring`: (60, 0.2), (50, 2.0), (35, 6.7) score 61.2, 60.0, 58.45 and sort in that order; ties by sources, newest, id; the divisor is a parameter |
| AC-2 no tone means coverage only | TC-2, TC-15 | pass | `test_scoring` (all-null and key-absent windows rank by coverage, one non-null switches the note, a missing tone counts 0); `test_cycle` (every call carries `include=["tone_neg"]`; the file says "Ranked by outlets covering a story." or "… and negative tone."); `test_mcp` (`include` sent only when given) |
| AC-3 reworded headlines become one group | TC-3, TC-6 | pass | `test_grouping`: every one of the 9 real same-event pairs (Murphy, Stevens, jet crash, Western Sahara, childcare fine, Trump rally, Alaska ruling, Lori Vallow Daybell, Florida plane) is one group with summed sources, the shown headline has the most sources, the other is "Also" |
| AC-4 different events stay apart | TC-4, TC-6 | pass | all 5 real different pairs stay two groups; four "Field Level Media Top 25" headlines from one domain stay four groups, and merge without the same-domain guard (the guard is what keeps them apart); no chaining |
| AC-5 the time window | TC-5 | pass | 47 h 59 min merges, 48 h 01 min does not, 24 h setting splits the first; applies in both directions from the seed |
| AC-6 Top stories block | TC-7, TC-19 | pass | `test_sections` + `test_render_stories`: the best 5 in order, each once in the file, a shorter block when fewer qualify; the hand-written golden file matches byte for byte |
| AC-7 sections use fixed labels | TC-8, TC-9 | pass | vote over theme hits (the second label ahead wins), ties to the label listed first, no hit or fewer than `section_min_hits` goes to "Other", order by best score, caps hold, JSON override validated at start |
| AC-8 single-source stories are not listed | TC-10 | pass | an hour of singles writes the "No story was carried by 2 or more outlets this hour." file, acks, makes no model call; only groups with enough sources are listed; the minimum is a setting |
| AC-9 the model is asked only about multi-headline groups | TC-11 | pass | exactly one call with exactly the group's titles (shown first, at most 1 + `also_per_group`), none for a single-headline group; the prompt text is pinned and carries no label, count or URL |
| AC-10 a failed model call degrades one line | TC-12 | pass | one raising and one silent summariser: those groups keep their links, the healthy group keeps its sentence, file written, cursor acked |
| AC-11 hostile text is escaped | TC-13 | pass | a stdlib link reader finds one well-formed link per story in the Top block and a section; titles decoded once; model text escaped (`\*`, `\<`, `\[`) |
| AC-12 file first, then ack | TC-14 | pass | recorded order `list`, `write`, `ack:c1`, one ack; on `OSError` there is no ack and the next cycle re-reads and writes |
| AC-13 the theme digest is gone | TC-16, TC-9 | pass | `test_removed`: the three modules, the old functions and the nine settings are gone; a text scan of source, tests, README, Makefile, compose, `.env.example` finds no old term; an environment that still sets the old variables starts; a cycle writes only `YYYY-MM-DD/HHMM.md` and `latest.md` |
| AC-14 old output is removed once, on request | TC-17, TC-18 | pass | `test_cleanup` (13): dry run lists exactly the old files and deletes nothing, the real run deletes exactly those and the emptied folders, new files are byte-identical; unknown, unreadable and symlinked entries are kept; missing and empty folders are a no-op; the loop never calls it. Also done for real on the owner's folder (above) |
| AC-15 a real hour reads well | TC-20 (manual) | **manual-ok with known gaps** | the owner ran `make once` on the live platform on 2026-11-02: it worked end to end; the owner's verdict was that the **summaries and categories are bad**. The "clearer than the theme digest" part was not confirmed. Accepted as a demo limitation (F-1, F-8) |

## Owner's live read (2026-11-02)

The owner ran a real cycle against the live platform with their own key. Reported: *it worked, but the summary and categories are bad*. Nothing more specific was recorded, and no cause is claimed here. What was already measured offline and is the likely background: theme codes are noisy, so sections misfile stories (about 60% looked right in the sample read), and the small local model writes one sentence from headlines only. The owner's decision: **mark it in the docs, and come back only if there is time, because it is just a demo.**

## Measurements

| ID | What | Result |
|---|---|---|
| M-1 | Grouping time on a real hour | **0.025 s** for 1 613 articles (5 runs, 0.025 to 0.026): 1 576 groups, 84 with 2+ sources |
| M-2 | How full the digest is (3 real hours, production code and defaults, `source_count` as seen right after the hour) | every hour fills a Top 5 and all 6 sections: 07:00 137 groups with 2+ sources, 29 listed; 08:00 85, 28 listed; 09:00 93, 29 listed; 4 groups per hour land in "Other" (the cap) |
| M-3 | Merge quality | 14 labelled pairs correct (9 same, 5 different) plus the template headlines; 20 merged groups hand-checked on the 08:00 hour: **18 clearly the same story, 2 ambiguous** (an FCC pair, and two "war film on Netflix" articles that share a clickbait template), **no clear false merge**. Known misses remain (some rewordings stay separate, for example one Murphy variant in the spike) |
| M-4 | Cycle time with the real model | **4.4 s total** on the 08:00 hour: 8 model calls (4.3 s in the model) against a possible 29, because only groups with 2+ distinct headlines get a sentence; 0 empty answers; budget of one hour not close |
| M-5 | Late growth (risk 1) | spike: for each of the 3 hours, **all five** of the final top-5 stories (today's counts) were already in the early top 10. The hourly view is less hurt by late growth than feared |

Quality read of the real digest (08:00 hour, a quiet hour). The model sentences were accurate one-liners of their headlines ("The UN's peacekeeping mission in Western Sahara ends after 35 years."; "Three AAP MLAs from Punjab are joining the BJP ahead of the 2027 Punjab Assembly elections."). Links, "Also" lines, source counts and labels all rendered correctly. What is weak is the content the data supports: the Top 5 held the UN mission and the Binance hack next to "One million face losing landline" and a childcare fine, and the sections hold some misfiles ("'Spectacular' war film on Netflix" under Conflict & Security, "Rare Cadbury chocolate bar" under Business, company press releases under Politics). This is the spike's finding (coverage measures syndication reach; theme codes are noisy), accepted in decision D-11. Press releases are 1.3% of all URLs; in the 08:00 hour 4 of the 28 listed stories were press releases, none in the Top 5, and none in the other two hours.

## Doc drift

Fixed in this stage: `design-detail.md` named concepts but not the functions that implement them; it now has a code map (§11) listing each component's module and main names. Checked by script: every name the design promises exists in the code; the README's settings table matches `Settings` (0 problems); ADR-0031 is Accepted; CLAUDE.md, the roadmap and the `what-happen` docs (with a "superseded for the digest shape" banner) agree with the code.

Changes made during implementation that differ from the approved docs, all recorded where they belong:

- **D-11 (user, after the spike):** keep copies-times-tone scoring, strip trailing outlet segments, add `section_min_hits`; the proper fix for syndication inflation is a platform `domain_count` (backlog).
- **`clean_title` strips repeated trailing segments** (found on the real hour: `… | WKZO | Everything Kalamazoo`, 9 of 1 613 titles), while three or more words remain in front. Design-detail §2 updated.
- **AC-7** reworded from "first matching label" to the vote (design review, user-approved).
- **`StoryGroup.variants` counts distinct cleaned headlines** (two articles differing only by an outlet suffix are one headline; coverage still counts both); the renderer and the model use it.
- **The new renderer and prompt were added next to the old ones** in T-05 and the old ones deleted in T-07, so the suite stayed green after every task.
- **Section labels are rendered unescaped** (operator configuration, not article data), so "Politics & Government" is not shown as `Politics \& Government`.

## Scope

Nothing implemented outside the spec. Not built, on purpose: a rolling window, embeddings or platform clustering, a press-release blocklist, region headings, a model-chosen label, a web page, any platform change. The old theme digest's code, tests, settings, docs and output were removed as decided (D-1, D-2).

## Verdict and follow-ups

**Pass with follow-ups.**

| ID | Priority | Follow-up |
|---|---|---|
| F-1 | closed | **AC-15, the owner's live read: done 2026-11-02.** It worked end to end; summaries and categories were judged bad (F-8). If you run it again with the platform API rebuilt from `tone-in-summary`, the ranking note will say "and negative tone" |
| F-2 | P1 | Platform `domain_count` in the article summary, so syndication networks stop inflating coverage (the proper fix for the soft items in the Top 5). A platform spec, not an agent change |
| F-3 | P2 | If the hourly Top 5 is not satisfying after a day: the rolling 24-hour read (backlog P1). M-5 suggests the hourly view is less affected by late growth than feared, so this is about breadth of coverage, not correctness |
| F-4 | P2 | Section quality: roughly 60% of sectioned stories look right in the read; try `WHATHAPPEN_SECTION_MIN_HITS=2` (more in "Other", fewer misfiles) or a model-chosen label |
| F-5 | P3 | A press-release filter by URL path (`/press-releases/`, `newswire`): 1.3% of URLs, 4 of 28 listed stories in one of three hours |
| F-6 | P2 | A CI job for `agents/whathappen` (path-filtered, `make -C agents/whathappen check`); the root `make check` does not cover it (carried over from the first digest) |
| F-7 | P3 | Commit the working copy (T-07 to T-09) and open a draft PR; nothing here is pushed |
| F-8 | P3 | **Summary and category quality (owner's verdict on the live read; demo, may not be revisited).** Things to try first, in order of cost: `WHATHAPPEN_SECTION_MIN_HITS=2`; a larger Ollama model or a stricter prompt; a model-chosen section label; dropping the model sentences and showing headlines only. 2026-11-04: the summary half is addressed — sentences are now grounded in the stored page text over `get_article` (`WHATHAPPEN_SUMMARY_BODY_CHARS`, body-extraction backlog "digest reads bodies"); section labels are unchanged |
