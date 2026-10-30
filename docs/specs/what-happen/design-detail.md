# what-happen — Design detail

Reference only: not required reading for approving the design (see [design.md](design.md)).

## 1. Settings (section `agent` in `infra/config/newsdock.yaml`; env `NEWSDOCK_AGENT_<NAME>`)

All are new fields on `newsdock_agent.config.Settings` with the default below; the digest service shares the class with the scoring loop. Values marked provisional are measured in T-01.

| Setting | Default | Meaning |
|---|---|---|
| `digest_interval_seconds` | 3600 | sleep between cycles |
| `digest_dir` | `infra/digests` (compose: `/digests`) | output root; a root `digests/` folder fails `check_layout` (spike §4) |
| `digest_state_file` | `infra/digests/digest-baseline.json` (compose: `/data/digest-baseline.json`) | baseline file; inside the git-ignored output folder so an ad-hoc run never litters the repo root |
| `digest_model` | `qwen3:4b-instruct` | summary model (chosen in T-01, spike §3) |
| `digest_max_themes` | 8 | sections per digest (provisional) |
| `digest_stories_per_theme` | 3 | linked stories per section (provisional) |
| `digest_prompt_titles` | 3 | titles sent to the model per theme; equal to `digest_stories_per_theme` on purpose, so every sentence can be checked against the links shown (T-11: with 8 titles the sentence described stories the reader could not see) |
| `digest_min_theme_count` | 5 | smallest window count that may be listed (provisional) |
| `digest_skip_theme_prefixes` | `TAX_,WB_,EPU_,CRISISLEX_,USPEC_,UNGP_,GENERAL_,MEDIA_,SOC_,LEADER,AFFECT` | comma-separated generic prefixes to drop (spike §2.3) |
| `digest_max_articles` | 20000 | cap per cycle (provisional) |
| `digest_baseline_hours` | 24 | entries kept |
| `digest_baseline_min_entries` | 3 | below this the ranking is cold |
| `digest_baseline_themes_kept` | 2000 | themes with count ≥ 2 stored per entry (file size bound; provisional) |
| `digest_summary_max_chars` | 300 | cut a model line longer than this |

Reused: `ollama_url`, `ollama_timeout_seconds`, `ollama_temperature`, `batch_limit` (page size, ≤ the API's 200), `mcp_url`, `api_key`, `heartbeat_file`. The heartbeat's allowed age is `2 × digest_interval_seconds + ollama_timeout_seconds × digest_max_themes`.

The digest service sets `NEWSDOCK_AGENT_API_KEY` from `NEWSDOCK_DIGEST_API_KEY` in `.env` and `NEWSDOCK_AGENT_AGENT_NAME` is unused (the key names the agent). No database or Kafka keys exist (`extra="forbid"`, AC-15).

## 2. Cycle algorithm (C-51)

```
cycle(now):
  articles, cursor = [], None
  loop:
    page, next = mcp.list_new_articles(limit=batch_limit, cursor=cursor)   # cursor None on page 1
    articles += page ; cursor = next
    stop if len(page) < batch_limit or len(articles) >= digest_max_articles
  if no articles: log "empty window"; return            # AC-11: no file, no ack
  counts = count_themes(articles)                       # each theme once per article
  ranked = rank_themes(counts, len(articles), baseline, settings)
  picks  = pick_stories(ranked, articles, K)
  summaries = {theme: summarise(theme, titles) or None}  # per theme, failures -> None
  text = render(now, window, ranked, picks, summaries)
  writer.write(now, text)                               # atomic; raises -> no ack (AC-3)
  mcp.ack_cursor(cursor)                                # AC-2
  baseline.append(entry(now, len(articles), counts)); store.save(baseline)   # best effort
```

An empty page returns the same cursor (`service.list_new`), so the final cursor is always the last non-empty page's, or the agent's stored position.

## 3. Ranking (C-52)

- `window_count[t]` = articles whose `themes` contain `t` (a theme counted once per article). Themes with an empty list add nothing.
- Dropped: themes starting with a skip prefix, and `window_count < digest_min_theme_count`.
- **Warm** (`len(entries) ≥ digest_baseline_min_entries`): `share[t] = Σ entry.themes[t] / Σ entry.articles`; `expected = max(share[t] × window_articles, 1.0)`; `rise = window_count / expected`. Sort by `rise` desc, then `window_count` desc, then code. The heading shows `×rise` rounded to one decimal.
- **Cold**: sort by `window_count` desc; no rise shown; the digest line says "no baseline yet".
- The first `digest_max_themes` remain.
- `expected` is floored at 1 so a brand-new theme gets `rise = window_count`, not infinity.

## 4. Story picking (C-53)

For each ranked theme in order: candidates = articles with that theme not yet taken by an earlier theme; sort by `source_count` desc, `published_at` desc, `article_id`; **take `digest_prompt_titles`** of them (the theme's own stories). The first `digest_stories_per_theme` are shown as links; all taken ones are the titles sent to the model. The theme's "N stories" in the heading is `window_count` (all articles with the theme, taken or not). Reason (spike §2.5): the most widely covered stories carry many themes, so letting them into every prompt made every summary the same.

## 5. Rendering (C-54) and prompt

Layout is exactly the sample in spec §5. Rules:

- Heading line: `# What happened · YYYY-MM-DD HH:MM UTC (N articles · since HH:MM)`; `since` is the time of the previous baseline entry, or `first run` when there is none. No range from `published_at`: real data has dates years off (spike §2.1).
- Titles are passed through `html.unescape` once before escaping (real titles carry `&#x2013;` and similar, spike §2.2); the same cleaned title goes into the prompt.
- Notice line: `> From headlines only. Summaries are written by a small local model and can be wrong; open the links.`
- Section: `## <rank>. <THEME LABEL> · ×<rise> vs usual · <N> stories` (or `· no baseline yet`), a blank line, the summary line or `Summary unavailable.`, then the story lines.
- Story line: `- [<title>](<url>) · <domain> · <n> sources` (`1 source` singular; the domain is omitted when null).
- Escaping: in titles and summaries, `\` `[` `]` `` ` `` `*` `_` `<` `>` `|` get a backslash and control characters or newlines become one space; in URLs, space, `(`, `)`, `<`, `>` are percent-encoded. A title that is empty after cleaning renders as the URL.
- Label: the theme code with `_` replaced by a space.

Prompt (C-54), one user message, no system prompt:

```
Theme: ECON INFLATION
Headlines:
- <title 1>
- <title 2>
Write ONE plain sentence (at most 30 words) saying what these headlines are about.
Use only facts in the headlines. Do not add names, numbers or causes that are not there.
```

Answer handling (C-55): take the first non-empty line, strip list markers and quotes, cut at `digest_summary_max_chars`; empty or an HTTP/timeout error → `None` → "Summary unavailable.". Temperature from settings (0.0). No JSON schema (plain prose).

## 6. Baseline file (C-56)

```json
{"version": 1, "entries": [{"at": "2026-10-30T14:07:00Z", "articles": 1840, "themes": {"ECON_INFLATION": 58}}]}
```

Read: any error (missing, invalid JSON, wrong version, wrong shape) → empty baseline (cold start), logged once. Write: temp file in the same directory, `os.replace`. After append, entries beyond `digest_baseline_hours` are dropped from the front, and each entry keeps only its `digest_baseline_themes_kept` largest themes with count ≥ 2.

## 7. Files (C-56)

Write `HHMM.md` to a temp name in the same directory then `os.replace`; create the date directory as needed; then write `latest.md` the same way. If a file for that minute exists (two cycles in one minute) the later one wins. The text is also logged at INFO, one logger record per digest.

## 8. Compose and Makefile (C-58)

- Service `digest`: same build and image as `agent` (`newsdock-agent:dev`), `command: ["python", "-m", "newsdock_agent.digest"]`, `profiles: [apps]`, `networks: [agent]`, env `MCP_URL`, `OLLAMA_URL` as for `agent`, `NEWSDOCK_AGENT_API_KEY: ${NEWSDOCK_DIGEST_API_KEY:-}`, `NEWSDOCK_AGENT_DIGEST_DIR: /digests`, `NEWSDOCK_AGENT_DIGEST_STATE_FILE: /data/digest-baseline.json`; volumes: the config mount, `./digests:/digests` (that is `infra/digests/` on the host), named volume `digest_state:/data`; the same healthcheck module (`adapters.healthcheck` reads the heartbeat file).
- `.gitignore` gets `infra/digests/`; `.env.example` gets `NEWSDOCK_DIGEST_API_KEY=`; `make digest-once` runs one cycle on the host with `.env` loaded (key from `NEWSDOCK_DIGEST_API_KEY`) and writes to the same `infra/digests/`.
- A root `digests/` folder fails `check_layout.py` (DR-1), so the output lives under `infra/` (spike §4). The baseline stores only themes that are not skip-listed.

## 9. Failure table (full)

| Failure | Detected by | Result | Recovery |
|---|---|---|---|
| API down during paging | exception from C-57 | cycle aborts, no file, no ack | next interval |
| Key rejected (401) | `Unauthorized` | logged with a hint, no ack | fix key |
| Rate limit hit while paging | tool error | cycle aborts, no ack | next interval (600/min vs ≤ 100 pages) |
| Ollama down for every theme | each call fails | digest of links only, acked | none needed |
| Ollama slow | timeout per call | that section unavailable | none |
| Disk full or read-only | `OSError` in writer | no ack | next interval re-reads |
| Crash after the file, before the ack | restart | window re-read, second file | harmless |
| Crash after the ack, before the baseline | restart | one baseline entry missing | self-heals |
| Baseline corrupt | parse error | cold start | next cycle rewrites |
| Window above the cap | `len ≥ digest_max_articles` | partial digest, ack to that point | next cycle continues |
| Clock jump | none needed | file names may sort oddly | cosmetic |

## 10. Security

- No new network surface: the service only calls MCP (with its key) and Ollama.
- The key is env-only and never logged; settings reject database and Kafka keys.
- Markdown injection: all text from the data or the model is escaped (section 5); no HTML is produced.
- Prompt injection from headlines can only change a one-line summary; the model has no tools.
- Files are written under `digest_dir` with fixed names built from the clock, never from article text.
