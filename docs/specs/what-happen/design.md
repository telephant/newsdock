# what-happen — Design (M2g)

Status: design approved 2026-10-30, verified 2026-10-30 (by delegation: the user asked to finish the pipeline; the checklist below was resolved with the recommended answers, review them when you read this) · ADR-0029 Accepted (supersedes ADR-0028, which put the digest inside `apps/agent`).

Reading order: this file → [diagrams](diagrams/index.html) (open it) → [design-detail.md](design-detail.md) only if you need schemas and algorithms. Spec: [spec.md](spec.md).

The digest is an independent agent server in `agents/whathappen` (D-1, D-2, ADR-0029): its own project, image, compose file and `.env`, no platform code. It reads only through MCP, keeps one small JSON file of its own, and writes markdown files. No API, database, Kafka or web change.

## 1. Components

| Id | Job | Where / notes |
|---|---|---|
| C-50 | Digest entry: settings, wiring, the hourly loop, heartbeat, `--once` | `cli.py` (wiring, `--once`) and `domain/runner.py` (loop), started by `python -m whathappen` |
| C-51 | `DigestCycle`: one pass read → count → rank → pick → summarise → render → write → ack → baseline | `domain/digest.py`; works through ports, injectable clock |
| C-52 | Theme counting, ranking against the baseline, baseline rolling window | `domain/themes.py`, `domain/baseline.py`, plus the typed `domain/articles.py`; pure |
| C-53 | Story picker: top stories per theme, one theme per story | `domain/stories.py`; pure |
| C-54 | Markdown renderer (escaping, layout) and the per-theme prompt | `domain/render.py`, `domain/prompt.py`, shared cleaning/escaping in `domain/text.py`; pure |
| C-55 | Summariser: one Ollama `/api/chat` call per theme, plain-text answer | `adapters/summarize.py`; the model name is a setting |
| C-56 | Files: atomic digest writer (+ `latest.md`) and the JSON baseline store | `adapters/files.py` |
| C-57 | MCP client paging: `list_new_articles(limit, cursor=None)` | extends `adapters/mcp.py`; explicit cursor wins on the server (ADR-0017) |
| C-58 | Packaging: `Dockerfile`, `compose.yaml`, `Makefile`, `.env.example`, README, `WHATHAPPEN_*` settings | own network only; reaches the platform's published port and the host's Ollama |

Extension points (backlog, not built): a store port in C-51 for digests (web page), a label map in C-52, a `theme_prefixes` filter.

## 2. Key flows

- **F-40 One cycle** (diagram 2): page `list_new_articles` from the stored position with explicit cursors until a short page or the article cap → count themes → rank → pick stories → one summary per theme → render → write the file → `ack_cursor` → save the baseline.
- **F-41 Hourly loop** (diagram 3): run a cycle at start, sleep `interval_seconds`, repeat; a failing cycle is logged and the loop continues; the heartbeat is written after every pass.

## 3. Contracts

Reads (already in the API, unchanged):

| Call | Use |
|---|---|
| `list_new_articles(limit=200, cursor?)` | no cursor on page 1 (server resumes the agent's position, or the last hour for a new agent); then the previous `next_cursor` |
| `ack_cursor(cursor)` | once, with the last `next_cursor`, after the file is written |

Local files (the only state):

| File | Content |
|---|---|
| `<output_dir>/YYYY-MM-DD/HHMM.md` (UTC run time) | one digest |
| `<output_dir>/latest.md` | copy of the newest digest |
| `<state_dir>/digest-baseline.json` | `{version, entries: [{at, articles, themes{code: count}}]}`, newest 24 entries |

## 4. The tricky parts

1. **Ack order = at-least-once.** File first, then ack, then baseline. A crash before the ack re-reads the window and writes a second file for it (harmless); a crash after the ack loses one baseline entry (a cache). Never the other way round.
2. **Rise is share-based.** `rise = count / (pooled baseline share × articles in this window)`. For equal-size windows it equals "count ÷ usual count" (AC-4), but a short window after a restart or a long catch-up window does not distort it. This refines D-7 (see checklist).
3. **One story, one theme.** Themes are walked in rank order; each takes its top stories that no earlier theme took. Counts in the heading stay per theme.
4. **The model writes, Python counts.** The prompt holds only the theme label and titles. A bad or missing answer degrades one section (D-9).
5. **Window cap.** At `max_articles` the cycle stops paging, digests what it read and acks that position; the next cycle continues (catch-up), so no article is skipped.
6. **Own key, own cursor.** The digest service has its own registered agent; sharing the demo agent's key would make the two loops steal each other's articles.
7. **Untrusted text.** Titles and the model's lines are escaped as markdown text; headlines can contain anything, including instructions aimed at the model, which can only change a one-line summary.

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| Ollama down or slow | sections show links and "summary unavailable"; digest written, acked |
| API down or key rejected | no digest, no ack; logged; retried next interval |
| Digest directory not writable | no ack; retried (AC-3) |
| Baseline file missing or corrupt | cold start; rewritten after the cycle |
| Window above the cap | digest of the first part, ack, continue next cycle |

## 6. Technology

Python 3.12, `httpx` (Ollama), the `mcp` client library (its own copy of the small wrapper), `pydantic` settings, stdlib `json`, `pathlib`, `os.replace`. Nothing new to install **[verified]**: all are already dependencies of `apps/agent`. No ADR-worthy library choice; one ADR for the placement (ADR-0028).

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1 | C-51, C-57 (F-40) |
| AC-2 | C-51 (F-40) |
| AC-3 | C-51, C-56 |
| AC-4 | C-52 |
| AC-5 | C-52, C-56 |
| AC-6 | C-53 |
| AC-7 | C-54 |
| AC-8 | C-54 |
| AC-9 | C-54 |
| AC-10 | C-51, C-55 |
| AC-11 | C-51 |
| AC-12 | C-56 |
| AC-13 | C-50 (F-41) |
| AC-14 | C-52, C-56 |
| AC-15 | C-58 |
| AC-16 | C-50…C-58 (manual) |

## 8. Questions to answer before approving this design

- [x] Is the share-based rise (tricky part 2) acceptable as a refinement of D-7? Resolved: yes (recommended; AC-4 unchanged).
- [x] Is "file, then ack, then baseline" the right order? Resolved: yes, a duplicate digest is cheaper than a lost window.
- [x] Is catch-up over several cycles (cap, tricky part 5) better than skipping to the newest articles? Resolved: yes, nothing is silently dropped; a skip option is in the backlog if it proves slow.
- [x] Is one summary per theme (about 8 model calls per hour) the right cost? Resolved: yes, each call is a few titles and seconds.
- [x] Is a bind-mounted folder (`agents/whathappen/output/`, git-ignored; a root `digests/` fails the layout check) the right place for the output? Resolved: yes, you open the files from the host.
