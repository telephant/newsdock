# what-happen — T-01 spike findings (2026-10-30)

> **Relocated 2026-10-30 ([ADR-0029](../../adr/0029-whathappen-as-an-independent-agent-server.md)).** This report describes the agent while it lived inside `apps/agent` (module `newsdock_agent.digest`, settings `digest_*`, `make digest-once`, `infra/digests/`). The code now lives in `agents/whathappen/` (package `whathappen`, variables `WHATHAPPEN_*`, `make -C agents/whathappen once`, `agents/whathappen/output/`). Findings and measurements below still hold.

Run against the live dev stack (Postgres, API, Ollama on the host), with a throwaway registered agent `whathappen-spike` (it stays registered in the dev database; disable it in the UI when you like). Scripts were kept outside the repo. All numbers below are **[verified]** this session unless marked.

## 1. Data volume and shape

| Measure | Result |
|---|---|
| Articles in the first-run window (the server's "last hour") | 2 562, read in 13 pages of 200 in 0.5 s (0.04 s per page) |
| Articles with an empty theme list | 214 (8 %) |
| Articles with `source_count` > 1 | 138 (5 %) |
| Distinct themes in that window | 3 181; with count ≥ 2: 2 091 |
| Paging with explicit cursors | works as designed: the last page is short, no extra page needed |

Consequences: `digest_max_articles` 20 000 gives about 8 hours of headroom (kept). 100 pages at most per cycle is far below the 600 requests per minute limit. A baseline entry of about 2 000 themes is roughly 75 KB, so 24 entries are about 2 MB (kept at `digest_baseline_themes_kept` 2 000).

## 2. Findings that contradict the design

1. **`published_at` is not reliable for a window range.** At least one article in the window is dated 2004 while the rest are 2026. The heading cannot show "window = min–max `published_at`". **Change:** the heading shows the run time, the article count and "since HH:MM" (the previous baseline entry's time, or "first run" when there is none).
2. **Titles contain HTML entities** (`&#x2013;`, `&#x20AC;`, `&#x2014;` seen in real titles). **Change:** the renderer and the prompt builder run `html.unescape` once on titles before markdown escaping.
3. **GDELT themes are mostly generic at hour scale.** The 40 most frequent themes are taxonomy codes (`UNGP_*`, `CRISISLEX_*`, `EPU_*`, `WB_*`, `USPEC_*`, `TAX_*`, `GENERAL_*`, `LEADER`, `AFFECT`). Prefix mass: WB 18 050, TAX 15 902, EPU 3 965, CRISISLEX 2 930, USPEC 1 432, UNGP 1 329, SOC 1 218, ECON 1 086, GENERAL 962, MEDIA 552. **Change:** the skip-list default is filled: `TAX_,WB_,EPU_,CRISISLEX_,USPEC_,UNGP_,GENERAL_,MEDIA_,SOC_,LEADER,AFFECT` (`SOC_` is an **[assumption]**, its contents were not read).
4. **A share cap on themes did not help.** Dropping themes present in more than 10 %, 5 % or 3 % of the window removed almost nothing (1 185 → 1 124 → 1 062 themes with count ≥ 5), because no theme is above about 32 %; the prefix list does the work. Not adopted.
5. **Theme groups are often not coherent, even after the skip-list.** Under `PROTEST` the top headlines were about an import expo, a drug-driving law and an EV launch; under `IDEOLOGY` about politics, medicine and weather. The most widely covered stories carry many themes, so they land in every group. The model is not the cause: it correctly says "cover diverse topics". **Changes made:** the story picker assigns up to `digest_prompt_titles` stories per theme under the one-story-one-theme rule and the prompt uses a theme's own assigned stories (design-detail §4), so the same big story no longer appears in every prompt. **Not solved:** groups remain loose. Whether a warm baseline (spikes rather than volume) groups better is unmeasured and is a T-11 question. A real fix would cluster by story similarity (the embeddings exist in Postgres but are not exposed through MCP) and is recorded in the backlog.

## 3. Model comparison (same prompt, temperature 0, 5 themes, host Ollama)

| | `llama3.2:3b` | `qwen3:4b-instruct` |
|---|---|---|
| Time per call | 0.2–2.7 s (first call loads the model) | 0.2–2.8 s |
| Invents facts | no | no |
| Style | vague ("cover various topics, including politics, technology…") | more concrete lists of the actual subjects, sometimes a run-on over 30 words |
| With a "answer exactly: Mixed stories." escape | ignores the format, rambles | answers "Mixed stories." for almost every theme (useless) |

**Decision:** default `digest_model` = `qwen3:4b-instruct`, the original prompt without the escape. Both are fast, so a cycle of 8 themes takes well under a minute. The `llama3.2:3b` model stays in use by the scoring agent, so Ollama holds two models (about 4.5 GB). The prompt stays as written in design-detail §5.

## 4. Output folder (R-1)

A root `digests/` folder fails `check_layout.py` (`DR-1 unexpected top-level entry`). `infra/digests/` passes. **Decision:** the bind mount is `./digests` relative to `infra/compose.yaml`, i.e. `infra/digests/` (git-ignored); `make digest-once` also writes there by default so both paths agree.

## 5. Settings decided

| Setting | Value |
|---|---|
| `digest_model` | `qwen3:4b-instruct` |
| `digest_skip_theme_prefixes` | `TAX_,WB_,EPU_,CRISISLEX_,USPEC_,UNGP_,GENERAL_,MEDIA_,SOC_,LEADER,AFFECT` |
| `digest_min_theme_count` | 5 (unchanged) |
| `digest_max_articles` | 20000 (unchanged) |
| `digest_baseline_themes_kept` | 2000 (unchanged); only themes that are not skip-listed are stored, which makes the file smaller still |
| `digest_dir` default | `infra/digests` on the host, `/digests` in the container |

## 6. Fixture

`apps/agent/tests/fixtures/digest_window.json`: 30 real articles sampled across the window (public headline data only: id, title, url, domain, date, themes, source_count). Some titles keep their HTML entities on purpose (TC-11).

## 7. T-11 addendum (live run, 2026-10-30)

- **Prompt titles 8 to 3.** With 8 titles per theme and 3 links shown, the sentence described stories the reader could not see and read as a mash ("elections in Melaka, ads promoting Democrats, a play staged, daylight saving time"). With 3, the sentence is about exactly the three links shown, reruns are identical at temperature 0, and nothing was invented. `digest_prompt_titles` default is now 3 (equal to `digest_stories_per_theme`).
- **Cycle time.** 6 s for 1 932 articles including 8 model calls; Ollama down: 0.3 s and all sections degrade.
- **Baseline size.** 6.4 KB per entry (skip-listed themes are not stored), about 150 KB for 24.
- **Links.** Real hosts; many news sites answer a script with 451 or 403, so link checks need a browser.
- **Still unmeasured:** whether rising themes (warm baseline, 3 or more cycles) group more coherently than volume does. It needs the service to run for hours; `/spec-verify` or the owner can look at `infra/digests/` after a day.
