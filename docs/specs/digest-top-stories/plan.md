# digest-top-stories — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation

Run 2026-11-02 (commands in §6).

| # | Check | Result |
|---|---|---|
| 1 | Every AC has at least one test; no test without an AC | pass (AC-1 … AC-15 ← TC-1 … TC-20) |
| 2 | Every AC maps to design components; every AC is implemented by a task | pass |
| 3 | Names consistent across spec, design, diagrams, tests, tasks (`StoryGrouper`, `LexicalGrouper`, `min_group_sources`, `top_stories`, `section_labels`, `tone_divisor`, `clean-old`, the `<!-- whathappen:story-first -->` marker, C-70…C-79) | pass |
| 4 | No doc treats a Proposed ADR as decided | pass (ADR-0031 is Accepted 2026-11-02) |
| 5 | Untagged claims, invented numbers, missing glossary terms | pass; the thresholds are listed as provisional targets in spec §7 and measured in T-01 and M-1…M-5 |
| 6 | Nothing from `backlog.md` leaked into scope | pass (no rolling window, embeddings, blocklist, region sections, web page) |
| 7 | Open questions and unchecked checklist items | none; design §8 is fully ticked |

Findings fixed while planning: the cleanup's Makefile targets aligned between design and task T-08; AC-7 reworded from "first matching label" to the vote (design review 2026-11-02). Open risks carried into implementation: **R-1** an hourly window may yield too few multi-source groups for a full Top block (de-risked first by T-01 on real hours); **R-2** the grouping thresholds come from one day of data (T-01 and M-3); **R-3** late-growing stories rank low by decision D-6 (measured by M-5, backlog item); **R-4** the old output to delete lives in the owner's main checkout, outside this worktree, so the real deletion is a confirmed step in T-09.

## 1. Spike first

**T-01** runs the biggest unverified claim on real data before anything is built: the grouping and ranking prototype was measured on one day of articles with two or more sources, but the digest sees one hourly window that also contains thousands of single-source articles. T-01 exports three real hourly windows, runs the prototype on them and records the group counts, how many groups reach 2 sources, whether the Top 5 is sensible, the grouping time (about 2 000 titles), and the labelled pairs for the tests. If the Top block is thin, `min_group_sources`, the caps or the window are revisited with you before T-02.

## 2. Tasks (walking skeleton order)

| Task | Title | Implements | Components | Depends on |
|---|---|---|---|---|
| T-01 | Spike: real hourly windows, fixtures, thresholds | (de-risks AC-3…AC-8, AC-15) | C-71, C-72, C-74 | — |
| T-02 | Title tokens and the lexical grouper | AC-3, AC-4, AC-5 | C-71, C-72 | T-01 |
| T-03 | Story groups and scoring | AC-1, AC-2 | C-73 | T-02 |
| T-04 | Selection and sections | AC-6, AC-7 | C-74 | T-03 |
| T-05 | Prompt and renderer | AC-6, AC-8, AC-9, AC-11 | C-75, C-76 | T-04 |
| T-06 | Cycle rewire and MCP `include` | AC-2, AC-8, AC-9, AC-10, AC-12 | C-70, C-77 | T-05 |
| T-07 | Remove the theme digest | AC-13 | C-79 | T-06 |
| T-08 | Cleanup command for old output | AC-14 | C-78 | T-07 |
| T-09 | Docs, live run and the one-time cleanup | AC-15 | C-70…C-78 | T-08 |

Milestones: after **T-04** the pure pipeline (group, score, select) works on the real fixtures (AC-1…AC-7); after **T-06** a cycle produces a story-first file against fakes (AC-8…AC-12); after **T-07** nothing of the theme digest remains; after **T-09** a real hour has been read by you.

## 3. Effort (rough, one person with an assistant)

| Phase | Tasks | Estimate |
|---|---|---|
| Spike and fixtures | T-01 | 1.5 h |
| Pure domain | T-02, T-03, T-04 | 3 h |
| Render and cycle | T-05, T-06 | 3 h |
| Removal and cleanup | T-07, T-08 | 2 h |
| Docs and live run | T-09 | 1.5 h |
| **Total** | | **about 11 h** |

## 4. Definition of done (every task)

- Tests are written first and seen to fail, then green.
- `make -C agents/whathappen check` (ruff, ruff format, mypy strict, pytest) is green after each task; the root `make check` (layout rule for `agents/`, docs check) is green at T-07 and T-09.
- The agent stays independent: no import of `newsdock*`, `apps` or `packages` (`test_packaging.py`).
- Docs a task touches are updated in the same edit; no secrets; the agent's `.env` is never read by tests.
- Pure modules in `domain/` do no I/O; I/O is in `adapters/`; the environment is read only in `config.py`.

## 5. Out of scope for this plan

A rolling window, embeddings or platform clustering, a wire-domain blocklist, region headings, a model-chosen label, a web page for digests, any platform change (all in [backlog.md](backlog.md)).

## 6. Validation commands run

```
python plan_check.py   # AC <- TC rows, TC <- tasks, AC <- tasks, Proposed mentions, unchecked boxes
uv run python infra/scripts/check_docs.py
```

## 7. Status

| Task | Status |
|---|---|
| T-01 | ✅ 2026-11-02 — spike on three real hours ([spike.md](spike.md)): 85–137 listed groups per hour, grouping 0.02 s, late growth smaller than feared (the final top 5 were all in the early top 10); finding: coverage measures syndication reach, soft items fill 1–2 of 5 Top slots; decision D-11 (user): keep the design, strip " \| outlet" suffixes, add `section_min_hits`; fixtures `story_window.json` (1 613 rows, 715 KB) and `story_pairs.json` (14 pairs + 4 template rows) committed |
| T-02 | ✅ 2026-11-02 — `domain/titles.py` (`clean_title`, `title_tokens`, `MatchParams`, `matches`), `domain/grouping.py` (`StoryGroup`, `StoryGrouper`, `LexicalGrouper`), `Article.tone_neg`; `test_titles.py` 21 + `test_grouping.py` 17 passed (real pairs, template headlines, window boundaries, no chaining, input-order independence, index equals brute force on the real hour); agent suite 167 passed, ruff and mypy strict green; **M-1: 0.025 s for 1 613 articles (1 576 groups, 84 with 2+ sources)** |
| T-03 | ✅ 2026-11-02 — `domain/scoring.py` (`ScoredGroup`, `score_groups`, `RANKING_COVERAGE` / `RANKING_TONE`): `sources × (1 + tone_neg / divisor)`, ties by sources, newest, id, coverage-only fallback; `test_scoring.py` 12 passed; agent suite 179 passed, ruff and mypy strict green |
| T-04 | ✅ 2026-11-02 — `domain/sections.py` (`DEFAULT_SECTIONS`, `parse_section_labels`, `label_for` by vote with `min_hits`, `select` → `Selection`/`Section`): minimum sources, Top block, labels by theme-hit vote, ordering by best score, caps, one listing per group; `test_sections.py` 23 passed; agent suite 202 passed, ruff and mypy strict green |
| T-05 | ✅ 2026-11-02 — `render_story_digest` (marker, heading counts, ranking note, Top stories, labelled sections, "Also", quiet-hour sentence) and `group_prompt` added **alongside** the old `render_digest` / `theme_prompt` so the suite stays green until T-06 rewires the cycle and T-07 deletes the old ones; `StoryGroup` gained `key` and distinct-headline `variants` (`also` now lists distinct headlines only); `escape_markdown` (escape without a second decode); section labels render as operator config, unescaped; `test_render_stories.py` 20 + prompt 4 + grouping 2 new; golden file `digest_golden.md` hand-written first; agent suite 226 passed, ruff and mypy strict green |
| T-06 | ✅ 2026-11-02 — `DigestCycle` rewired (read with `include=["tone_neg"]`, group, score, select, one sentence per multi-headline group, render, write, then ack; no baseline), `McpClient.list_new_articles(include)`, `OllamaSummariser.summarise(titles)`, new settings in `config.py` (`section_labels` JSON validated at start, heartbeat age from the group counts), `cli.build_cycle` wiring; `test_cycle.py` rewritten (18), plus MCP, summariser, config and loop tests adjusted; agent suite 237 passed, ruff and mypy strict green. **Found on the real hour:** titles with two trailing segments (`… \| WKZO \| Everything Kalamazoo`, 9 of 1 613) kept a suffix, so `clean_title` now strips repeated trailing segments while 3+ words remain (design-detail §2 updated). First real-hour run: 1 613 articles in 9 pages → 28 stories, Top 5 plus 6 sections |
| T-07 … T-09 | todo |
