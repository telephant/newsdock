# digest-top-stories — Design detail

Reference only: not required reading for approving the design (see [design.md](design.md)). All code is under `agents/whathappen/src/whathappen/`.

## 1. Settings (`WHATHAPPEN_<NAME>`, also read from `agents/whathappen/.env`)

Provisional values were chosen from the prototype below and are re-measured at plan and verify. Unknown old keys in a `.env` are ignored (`extra="ignore"`).

| Setting | Default | Meaning |
|---|---|---|
| `top_stories` | 5 | groups in the Top stories block |
| `max_sections` | 6 | sections listed after the Top block |
| `groups_per_section` | 4 | groups per section |
| `min_group_sources` | 2 | a group below this is not listed |
| `also_per_group` | 3 | other headlines shown as "Also" and sent to the model (with the shown one: at most 4 titles) |
| `group_window_hours` | 48 | a headline joins a group only if published within this of the group's seed |
| `match_overlap` | 0.75 | overlap coefficient needed to merge |
| `match_jaccard` | 0.5 | Jaccard needed to merge (either rule suffices) |
| `match_min_shared` | 3 | at least this many shared significant words |
| `tone_divisor` | 10 | score = sources × (1 + tone_neg / divisor) |
| `section_min_hits` | 1 | theme hits a label needs to claim a group; below it the group goes to "Other" |
| `section_labels` | JSON, default in code (§4) | label → theme prefixes, in priority order |

Kept from M2g: `interval_seconds`, `output_dir`, `page_size`, `max_articles`, `model`, `ollama_*`, `summary_max_chars`, `mcp_url`, `api_key`, `log_level`, `heartbeat_file`. Removed: `max_themes`, `stories_per_theme`, `prompt_titles`, `min_theme_count`, `skip_theme_prefixes`, `baseline_hours`, `baseline_min_entries`, `baseline_themes_kept`, `state_file`. The heartbeat's allowed age becomes `2 × interval_seconds + ollama_timeout_seconds × (top_stories + max_sections × groups_per_section)`.

## 2. Grouping (C-71, C-72) — measured prototype, 2026-11-02

**Title cleaning** (`domain/titles.py`, `clean_title`): decode HTML entities, flatten whitespace, and drop trailing outlet segments (the text after the last ` | `, when it is 60 characters or fewer; sites append one, `| WKZO`, or two, `| Politics | News`, so a second segment goes only while at least three words remain in front of it). The cleaned title is what is shown and what is tokenised. About 14% of 2+ source rows carry such a suffix (T-01).

**Tokens** (`domain/titles.py`): lowercase, drop `'s`, replace characters outside `a-z0-9 '-` with spaces, drop words under 3 characters and a fixed English stop-word list, fold a trailing plural (`ies`→`y`, `s`), and truncate words longer than 6 characters to their first 6 (a cheap stemmer: `hospitalized`, `hospitalised`, `hospital` all become `hospit`). The result is a set.

**Match** (either rule, and at least `match_min_shared` shared tokens): overlap coefficient `|A∩B| / min(|A|,|B|) ≥ 0.75`, or Jaccard `|A∩B| / |A∪B| ≥ 0.5`.

**Algorithm** (`LexicalGrouper.group(articles)`):

```
order articles by source_count desc, published_at asc, article_id
groups = []; index = {token: [group ids]}
for article in order:
    candidates = groups reached through the article's tokens in `index`
    pick the first candidate g (in creation order) such that
        |published_at - g.seed.published_at| <= group_window_hours
        and article.domain not in g.domains          # same-domain guard
        and match(g.seed.tokens, article.tokens)
    if found: g.add(article) else: new group with article as seed; index its tokens
```

Matching only against the seed prevents chaining; the index keeps comparisons to groups that share a token. `sources` of a group = sum of members' `source_count`; the shown headline is the member with the most sources (ties: newest), which is the seed except on a tie; the other members are "Also".

**Prototype result** (`titles24`: 710 canonical articles with 2 or more sources from the previous 24 h; seed-based; stem 6; same-domain guard): 657 groups, 31 merged groups, largest 9 rows. Merged correctly: the Murphy stroke rewordings (9 rows, 152 sources), the Stevens/Rogers endorsement (5 rows, 71 sources; a second 2-row group of 60 sources stays apart), the Florida jet crash, the Western Sahara mission ending, the Alaska certification ruling. Known pairs: 4 of 4 decided pairs correct under the overlap rule. Observed failure without the guard: nine "Field Level Media Top 25: No. N Team" headlines merged on shared template words; the same-domain guard removes it. Remaining misses: some rewordings stay separate ("Sen. Chris Murphy suffers stroke…" forms its own group). A document-frequency cap on tokens was tried and rejected: it broke every real group, because an event's key words are frequent precisely because many rows report it.

## 3. Scoring and selection (C-73, C-74)

```
group.sources   = Σ member.source_count
group.tone_neg  = max(member.tone_neg for members that have it), else None
group.score     = sources × (1 + (tone_neg or 0) / tone_divisor)
```

If no article in the window has a non-null `tone_neg`, `ranking = "coverage"` and the header says "Ranked by outlets covering a story"; otherwise `"coverage and tone"`.

Selection: drop groups with `sources < min_group_sources`; sort by (score desc, sources desc, newest first, id); the first `top_stories` form the Top block; each remaining group gets a label (§4); sections are ordered by their best score, limited to `max_sections`; inside a section groups are ordered the same way and limited to `groups_per_section`. A group is listed once. Nothing is carried to the next hour.

## 4. Sections (C-74)

Default `section_labels` (provisional, filled from the theme counts of the same 24 h; tuned at verify). Order is the tie-break; only specific prefixes are used because generic codes are noisy on real data (EDUCATION, MANMADE_DISASTER_IMPLIED, SECURITY_SERVICES and KILL are left out of the map on purpose):

| Label | Prefixes |
|---|---|
| Conflict & Security | `ARMEDCONFLICT`, `MILITARY`, `TERROR`, `UNREST_BELLIGERENT`, `CEASEFIRE`, `EXTREMISM`, `DRONES` |
| Politics & Government | `ELECTION`, `LEGISLATION`, `DEMOCRACY`, `CONSTITUTIONAL`, `NEGOTIATIONS`, `ALLIANCE`, `IMMIGRATION`, `GOV_`, `VETO`, `RATIFY`, `RESIGNATION`, `SOVEREIGNTY` |
| Business & Markets | `ECON_`, `FUELPRICES`, `ENV_OIL`, `STRIKE` |
| Crime & Courts | `ARREST`, `TRIAL`, `CORRUPTION`, `PROTEST` |
| Health | `MEDICAL`, `HEALTH`, `DISEASE` |
| Disasters & Accidents | `NATURAL_DISASTER`, `EVACUATION`, `MARITIME_INCIDENT`, `TRAFFIC` |
| Other | (no match) |

**Vote:** for each label count, over all members of the group, the themes that start with one of its prefixes; the label with the largest count wins; ties go to the label listed first; fewer hits than `section_min_hits` (default 1) means "Other". Measured basis: a theme code alone mislabels (ARMEDCONFLICT on a DoorDash deal, MEDICAL on a Houdini story), so a group backed by several articles with the same label is more reliable than a single code.

`section_labels` is read from a JSON environment value when set; otherwise the default above (constant in `domain/sections.py`).

## 5. Rendering (C-75) and prompt (C-76)

```
<!-- whathappen:story-first -->
# What happened · YYYY-MM-DD HH:MM UTC (N new articles · M stories)

> New this hour, from headlines only. Ranked by outlets covering a story [and negative tone].
> Summaries are written by a small local model and can be wrong; open the links.

## Top stories
1. [Headline](url) · 112 sources
   One model sentence (only if the group has 2+ distinct headlines).
   Also: [Other headline](url), [Another](url)

## Politics & Government
- [Headline](url) · 51 sources
  …
```

- The marker is the first line; `N` is the number of articles read and `M` the number of groups listed.
- The story line is `[title](url) · <n> sources` (singular "1 source"); the domain is added when known: `· domain.com`. All text goes through `escape_text`; URLs through `encode_url` (unchanged).
- A quiet hour (articles read, no group with enough sources) renders the heading, the notice and `No story was carried by 2 or more outlets this hour.`; it is still written and acked.
- Prompt (one user message): the group's headlines only, `Write ONE plain sentence (at most 30 words) saying what these headlines report. Use only facts in the headlines. Do not add names, numbers or causes that are not there.` No counts, urls or labels are sent. Answer handling is `clean_answer` as before.

## 6. Cycle (C-70)

```
cycle(now):
  articles, cursor = page list_new_articles(include=["tone_neg"]) until a short page or max_articles
  if no rows: log "empty window"; return None            # unchanged: no file, no ack
  groups  = grouper.group(articles)                      # C-72
  ranked  = score(groups)                                # C-73
  chosen  = select(ranked, settings)                     # C-74
  lines   = {g.id: summarise(g.titles) for g in chosen if g has 2+ distinct headlines}
  text    = render(...)                                  # C-75
  path    = writer.write(now, text)                      # OSError -> no ack
  mcp.ack_cursor(cursor)
```

No baseline load or save. `Article` gains `tone_neg: float | None = None`.

## 7. Cleanup (C-78)

`python -m whathappen clean-old [--dry-run]` (`make clean-old` runs the dry run, `make clean-old-yes` deletes) works only inside `output_dir`:

- `baseline.json` is always old.
- `latest.md` and every `YYYY-MM-DD/HHMM.md` are old unless their first line is the v2 marker.
- Date folders left empty are removed. Anything else is ignored and listed as "kept".
- `--dry-run` prints the list and deletes nothing; without it the same list is deleted and reported. The loop never calls it.

## 8. Failure table (full)

| Failure | Detected by | Result | Recovery |
|---|---|---|---|
| API down during paging | exception from C-77 | cycle aborts, no file, no ack | next interval |
| Key rejected (401) | `Unauthorized` | logged with a hint, no ack | fix key |
| Platform returns no tone | no article has a non-null `tone_neg` | coverage-only ranking, header says so | rebuild the platform API |
| Ollama down for every group | each call fails | digest of links only, acked | none needed |
| Ollama slow | per-call timeout | that group has no model line | none |
| Disk full or read-only | `OSError` in the writer | no ack | next interval re-reads |
| Window above the cap | `len ≥ max_articles` | partial digest, ack to that point | next cycle continues |
| No story with enough sources | selection is empty | quiet-hour note, file written, acked | none |
| Old settings still in `.env` | `extra="ignore"` | ignored | remove at leisure |
| Grouping too slow | measured in verify | n/a (expected well under a second per thousand titles) | tune or index |
| Cleanup meets an unknown file | classification | kept and listed | none |

## 9. Security

- No new network surface: MCP with the agent's key and Ollama on the host, as before.
- Titles, domains and URLs are untrusted: cleaned, escaped as markdown text, URLs percent-encoded; no HTML is produced. A prompt-injection headline can only change one sentence (the model has no tools).
- File names come from the clock; the cleanup never leaves `output_dir`, never follows symlinks out of it, and deletes only files proven old.
- The key stays in `.env`; nothing about tone or grouping adds a secret.
