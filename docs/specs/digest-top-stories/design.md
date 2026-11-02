# digest-top-stories — Design (M2h)

Spec: [spec.md](spec.md) · Detail (reference only): [design-detail.md](design-detail.md) · Diagrams: [diagrams/index.html](diagrams/index.html) · ADR: [0031](../../adr/0031-story-first-digest-lexical-grouping-behind-a-port.md) (Accepted 2026-11-02)

**Reading order:** this file → the diagrams (each has a "Check" box) → the checklist at the bottom. Component ids start at C-70 (C-50…C-58 belong to what-happen, C-60…C-67 to tone-in-summary). The agent stays independent of the platform (ADR-0029): it changes only `agents/whathappen` and reads the platform through MCP.

The digest cycle keeps its skeleton (read, build, write, ack) and replaces the middle: theme counting and the baseline become **group, score, select**. Nothing is stored between cycles except the platform's cursor, so the cycle is stateless on disk.

## 1. Components

| Id | Job | Where / notes |
|---|---|---|
| C-70 | `DigestCycle`: read the window with tone, group, score, select, summarise, render, write, ack | `domain/digest.py` (rewired); ports unchanged except `list_new_articles(include)` |
| C-71 | Title tokens and the similarity rules | `domain/titles.py`; pure |
| C-72 | `StoryGrouper` port and the lexical grouper (seed-based, inverted index, time window, same-domain guard) | `domain/grouping.py`; pure |
| C-73 | Story groups and scoring `sources × (1 + tone_neg / tone_divisor)`, coverage-only fallback | `domain/scoring.py`; pure |
| C-74 | Selection: minimum coverage, Top stories, section labels by theme-prefix vote, caps and ordering | `domain/sections.py`; pure |
| C-75 | Markdown renderer: Top stories, sections, "Also" lines, notices, quiet-hour note, the v2 marker | `domain/render.py` (rewritten); escaping from `domain/text.py` unchanged |
| C-76 | Per-group prompt: headlines only | `domain/prompt.py` (changed: no theme label) |
| C-77 | MCP client: `list_new_articles(limit, cursor, include)` | `adapters/mcp.py` (one argument added) |
| C-78 | One-time cleanup of old output: `python -m whathappen clean-old [--dry-run]`; `make clean-old` is the dry run and `make clean-old-yes` deletes | `adapters/cleanup.py`, `cli.py`, `Makefile` |
| C-79 | Settings and removal of the theme digest (themes, baseline, their settings, tests, docs) | `config.py`; deleted: `domain/themes.py`, `domain/baseline.py`, `domain/stories.py`, the baseline store |

Extension points (backlog, not built): other `StoryGrouper` implementations (platform clustering), a rolling-window reader, a noise blocklist.

## 2. Key flows

- **F-70 One cycle** (diagram 2): page `list_new_articles(include=["tone_neg"])` → group → score → select → one sentence per group with 2+ headlines → render → write file → `ack_cursor`.
- **F-71 Selection** (diagram 1): drop groups under the minimum sources, sort by score, first five are the Top block, the rest go to labelled sections with caps.
- **F-72 Cleanup** (diagram 4): list files in `output/`, classify old versus v2 by content, delete only old ones (dry run lists).

## 3. Contracts

| Call / file | Content |
|---|---|
| `list_new_articles(limit=200, cursor?, include=["tone_neg"])` | articles with `tone_neg` (null when the article has none); an older API ignores `include` and the key is absent |
| `ack_cursor(cursor)` | once, after the file is written (unchanged) |
| `output/YYYY-MM-DD/HHMM.md`, `output/latest.md` | the digest; first line is the marker `<!-- whathappen:story-first -->` |
| Settings (`WHATHAPPEN_*`) | new: `top_stories`, `max_sections`, `groups_per_section`, `min_group_sources`, `also_per_group`, `group_window_hours`, `match_overlap`, `match_jaccard`, `match_min_shared`, `tone_divisor`, `section_min_hits`, `section_labels` (JSON, default in code). Removed: `max_themes`, `stories_per_theme`, `prompt_titles`, `min_theme_count`, `skip_theme_prefixes`, `baseline_*`, `state_file` |

## 4. The tricky parts

1. **Grouping must merge rewordings and not join events.** Measured on 710 real multi-source headlines (24 h): the rule below merges the Murphy, Stevens and jet-crash rewordings, keeps unrelated pairs apart, and one false-merge class (sports templates) is removed by the same-domain guard (design-detail §2, **[verified]** by a prototype on 2026-11-02).
2. **No chaining.** Articles join a group only if they match its *seed* (the best-covered headline), never another member, so one loose link cannot snowball into a mega-group.
3. **Cost.** About 2 000 titles per window; an inverted index (token → groups) limits comparisons to groups sharing a token. Measured at plan/verify.
4. **Tone may be absent.** The agent cannot tell "old platform" from "no tone" per article; it ranks by coverage and says so in the header when no article in the window has a non-null `tone_neg` (AC-2).
5. **Late-growing stories (risk 1).** Accepted by D-6: the hourly view sees early counts. The file says "new this hour".
6. **Ack order is unchanged.** File first, then ack; a crash before the ack re-reads the window and writes a second file (harmless).
7. **Cleanup safety.** The cleanup deletes only files it can prove are old (no v2 marker, or `baseline.json`), lists them first, never follows paths outside `output_dir`, and is never run by the loop.
8. **Sections are a weak signal.** Theme codes are noisy on real data (ARMEDCONFLICT tagged a company acquisition). A group's section is the label with the most theme hits across its articles, at least `section_min_hits`; below that it is "Other".
9. **Coverage is syndication reach (T-01 spike).** Station networks and newspaper chains inflate `source_count`; accepted, with outlet suffixes stripped from titles, and a platform `domain_count` recorded as the real fix (spec D-11).

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| Ollama down or slow | affected groups show links without the model line; digest written, acked |
| API down or key rejected | no digest, no ack; retried next interval (unchanged) |
| Output folder not writable | no ack; window re-read next cycle (unchanged) |
| No story with 2+ sources | file with a one-line note, still acked |
| Platform has no tone | ranked by coverage, header says so |
| Old output present | harmless; `clean-old` removes it on request |

## 6. Technology

Python 3.12 standard library for tokens and grouping (`re`, `html`, `collections`), the existing `httpx`, `mcp` client and `pydantic-settings`. Nothing new to install **[verified]**: every import is already used by the agent. One ADR for the grouping-behind-a-port and score decisions.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1 | C-73 |
| AC-2 | C-73, C-70, C-75 |
| AC-3 | C-71, C-72 |
| AC-4 | C-71, C-72 |
| AC-5 | C-72 |
| AC-6 | C-74, C-75 (F-71) |
| AC-7 | C-74 |
| AC-8 | C-74, C-75, C-70 |
| AC-9 | C-70, C-76 |
| AC-10 | C-70 |
| AC-11 | C-75 |
| AC-12 | C-70 (F-70) |
| AC-13 | C-79 |
| AC-14 | C-78 (F-72) |
| AC-15 | C-70…C-77 (manual) |

## 8. Questions to answer before approving this design

All six resolved 2026-11-02: recommended answers accepted (section vote, the measured grouping rule and caps, the v2 marker, label map in code with a JSON override, ADR-0031).

- [x] Section choice by **vote** (the label with the most theme hits across a group's articles, ties by configured order, none = Other) instead of "first matching label"? This rewords AC-7.
- [x] Is the measured grouping rule acceptable, including its known misses (a few rewordings stay separate) and the same-domain guard?
- [x] Is a first-line marker `<!-- whathappen:story-first -->` in each file an acceptable way to tell old output from new when cleaning?
- [x] Is "groups beyond the caps are simply not listed" acceptable (Top 5, at most 6 sections of 4)?
- [x] Should the default label map live in code with a JSON environment override, rather than a separate config file?
- [x] ADR-0031: accept the story-first design (lexical grouping behind a port, score by coverage and tone)?
