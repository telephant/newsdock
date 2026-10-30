# what-happen — Verify

> **Relocated 2026-10-30 ([ADR-0029](../../adr/0029-whathappen-as-an-independent-agent-server.md)).** This report describes the agent while it lived inside `apps/agent` (module `newsdock_agent.digest`, settings `digest_*`, `make digest-once`, `infra/digests/`). The code now lives in `agents/whathappen/` (package `whathappen`, variables `WHATHAPPEN_*`, `make -C agents/whathappen once`, `agents/whathappen/output/`). Findings and measurements below still hold.

Verified 2026-10-30 on branch `worktree-p2-delivery` (working copy, nothing committed yet). **Verdict: pass with follow-ups.** All 16 ACs hold; the follow-ups are the owner's browser link check, one Docker scene that cannot run beside the dev stack, and a quality question only hours of running can answer.

## What was run in this session

| Run | Result |
|---|---|
| `make check` (ruff, mypy strict, import-linter, layout, config, Python tests, web style/lint/format/types/tests, docs check) | exit 0; Python 793 passed (340 deselected: Docker/Ollama marks); web 181 passed |
| The 10 digest test files plus the config and MCP-client tests, run by name (`pytest -v`) | every test passed; the table below maps them to the ACs |
| Live cycle on the dev stack with a throwaway agent key | exit 0, 1 932 articles, 6 s, digest + `latest.md` written |
| Immediate second cycle | empty window, nothing written, nothing acked (`latest.md` unchanged) |
| `docker compose ... up -d --no-deps --build digest` | healthy after 6 s, digest written at start, file visible on the host, baseline in `/data`; container and volume removed afterwards |
| `make digest-once` through a temporary `.env` | without the key: guard message, non-zero exit; with the key: runs the cycle, exit 0 (window was empty: the container had acked it) |
| Ollama unreachable (`OLLAMA_URL` pointed at a closed port) | all 8 sections "Summary unavailable." with their links, digest written in 0.3 s |
| Docker isolation scene `test_agent_isolation.py` (TC-23) | **not run**: the dev stack holds ports 5433/29092/8000/3000 (`dev_stack_guard`); see follow-up F-2 |

## Results per acceptance criterion

| AC | Tests | Result | Evidence |
|---|---|---|---|
| AC-1 whole window | TC-1, TC-2, TC-3 | pass | 3 pages (200, 200, 37) → 437 articles, 3 calls, ack of the last cursor; a full last page asks for one more (empty) page; the cap stops after the page that reaches it and acks what was read; the client sends `cursor` only when given |
| AC-2 ack after the file | TC-4 | pass | recorded order `write`, `ack:c1`, `save`; one ack; the digest text is also logged |
| AC-3 failed write, no ack | TC-5 | pass | read-only directory: `OSError`, no ack, baseline untouched; next cycle on the same window writes and acks |
| AC-4 rising ranked by rise | TC-6, TC-7 | pass | A (×4.0) ranks above steady B (×1.0); skip prefixes, minimum count and max themes; unseen theme gets its count; a window twice the usual size does not double every rise |
| AC-5 cold start | TC-8, TC-9 | pass | under 3 entries: plain count order, no rise, "no baseline yet"; missing / empty / invalid / wrong-version / wrong-shape baseline loads as empty and a cold cycle completes |
| AC-6 stories per theme | TC-10 | pass | order by `source_count`, newest, id; a story with two ranked themes stays under the higher one; no story in two prompts |
| AC-7 safe links | TC-11, TC-12 | pass | hostile title and URL round-trip through a stdlib link reader; entities decoded once; singular/plural, missing domain, empty title shown as the URL |
| AC-8 layout | TC-13, TC-8 | pass | one `#`, one notice, `##` sections in rank order, nothing else; "first run" / "since" forms; the real 30-article sample renders cleanly |
| AC-9 prompt content | TC-14 | pass | the whole prompt text is pinned: label and titles only |
| AC-10 model failure | TC-15, TC-16 | pass | one raising and one `None` summary degrade only their sections, file written, cursor acked; six response shapes plus JSON of the wrong shape give `None`; live: Ollama unreachable, all sections degrade |
| AC-11 quiet hours | TC-17 | pass | no file, no ack, no baseline write, INFO line; also seen live |
| AC-12 atomic files | TC-18 | pass | `YYYY-MM-DD/HHMM.md` in UTC plus identical `latest.md`; no temp files; a failed rename keeps the old `latest.md`; also seen live (`cmp`) |
| AC-13 hourly cadence | TC-19 | pass | cycles at 0, 1 h, 2 h on a fake clock; a failing cycle does not stop the loop; heartbeat at start and after every pass; `--once` returns 0 or 1 |
| AC-14 baseline persisted and bounded | TC-20 | pass | 26 appends keep 24 and drop the oldest; skip-listed and rare themes not stored; failed save keeps the old file |
| AC-15 no route but MCP | TC-21, TC-22 (TC-23 not run) | pass | settings reject database/Kafka keys and match the config file; compose parse: agent network only, no DB/Kafka env, own key variable, agent image. TC-23 (Docker scene) is written and **not run**, see F-2 |
| AC-16 live run | TC-24 (manual) | pass, with the owner's link check open | see `tests.md` §4: files, equality, empty second window, healthy container, degrade path all done; summaries accurate to their three links; five links checked by script (1 loaded, 2 × 451, 2 × 403: real servers blocking a script) |

## Measurements

| What | Result |
|---|---|
| Articles per hour | 1 932 to 2 562 in the first-run window; 10 to 13 pages; 0.5 s to page |
| Cycle time | 6 s end to end including 8 model calls and a cold model load; 0.3 s when Ollama is down; budget of 10 minutes not close |
| Baseline file | 6.4 KB per entry; about 150 KB for 24 |
| Generic themes | most of the top 40; skip-list filled from them (spike §2.3) |
| Rise factors after a day | **not measured** (needs at least 3 stored cycles); F-3 |

## Doc drift

Fixed in this stage: spec §6 path (`infra/digests/latest.md`), design checklist wording, and the design component table (it now names `domain/articles.py` and `domain/text.py`, added during T-03 and T-05). Checked and consistent: the 14 `digest_*` settings are identical in code, `infra/config/newsdock.yaml` and the design-detail table (names and defaults, compared by script); compose service, Makefile target, `.env.example`, `.gitignore`, README, CLAUDE.md and roadmap agree on names; no Proposed ADR (ADR-0028 is Accepted).

Changes made during implementation that differ from the approved design, all recorded in the docs: share-based rise (D-7 refinement, design §4 point 2), heading without a `published_at` range (spike §2.1), titles decoded for HTML entities (§2.2), one-story-one-theme also for the prompt titles (§2.5), output folder `infra/digests/` (§4), `digest_prompt_titles` default 3 (T-11), baseline file default inside the output folder. The design was approved by delegation, so the owner should read design.md §8 and those items once.

## Scope

Nothing implemented outside the spec: no UI page, no database storage, no new MCP tool or API change, no label table, no region filter, no "Mixed stories" escape. The extra modules (`articles.py`, `text.py`) serve spec items.

## Verdict and follow-ups

**Pass with follow-ups.**

| ID | Priority | Follow-up |
|---|---|---|
| F-1 | P1 | Open five links from a digest in a browser (the script was answered 451/403 by four of five sites). Closes the last open box of AC-16 |
| F-2 | P2 | Run `make down`, then `make test-infra SCENE=e2e` to run TC-23 (the digest container's isolation and heartbeat); also still open from earlier verifies for the other Docker scenes |
| F-3 | P1 | Let the `digest` service run for a day, then read `infra/digests/`: do rising themes (×N vs usual) group more coherently than volume? If not, the backlog item "group by story similarity" is the fix |
| F-4 | P2 | Confirm the demo agent still scores after the image rebuild (its container was not recreated in this session) |
| F-5 | P3 | In the UI, disable the throwaway agents `whathappen-spike` and `whathappen-spike2`; create the real one with `make agent-create NAME=whathappen` and put its key in `.env` |
| F-6 | P2 | Backlog (already added): `published_at` outliers (an article dated 2004 in a live window) |

Next milestone candidates from the backlog: story-similarity grouping (needs an MCP tool for neighbours or vectors), body extraction (M3), or `/spec-verify forgot-password`, which is still pending from before.

## Relocation addendum (2026-10-30): moved to `agents/whathappen`

After the verdict above, the owner asked for the digest to be an independent agent server instead of a mode of the demo agent ([ADR-0029](../../adr/0029-whathappen-as-an-independent-agent-server.md)). The code moved with its tests; this is what was re-run after the move.

| Run | Result |
|---|---|
| `agents/whathappen`: `make check` (ruff, ruff format, mypy strict, pytest) | exit 0; **129 passed** (98 moved tests, plus 31 new: settings and `.env`, MCP client, heartbeat, packaging/independence) |
| Root `make check` (ruff, mypy, import-linter, layout incl. the new `agents/` rule, config, 681 Python tests, 181 web tests, docs) | exit 0; the demo agent's tests and settings are back to their pre-digest state |
| Independence test (`test_packaging.py`) | passes: no source or test file imports `newsdock*`, `apps` or `packages`; no workspace dependency; compose has no network, no `depends_on`, no database/Kafka env |
| Container, `docker compose build` then `run --rm whathappen python -m whathappen --once` against the running platform | exit 0, digest of 3 097 articles written to `./output` |
| Container as a service, `up -d --wait` | healthy in 5 s; attached to `whathappen_default` only; uid 1000 |
| `make once` on the host (with and without `.env`) | guard message without the key; with it the cycle ran (empty window: the container had read it) |

**New finding from the first container run (the point of an outside client):** the platform's MCP endpoint answered `421 Invalid Host header` to `Host: host.docker.internal:8000`, while the same container reached `/api/health` fine. The allow-list (`mcp_allowed_hosts`) is `localhost:*,127.0.0.1:*,api:*` and is pinned by the externalize-config snapshot, so the platform was not changed: the agent's compose file maps the name `api` to the host. Recorded in design-detail section 8, the agent README and ADR-0029.

**Changes to earlier results:** AC-15 now reads "the agent server is independent of the platform" (TC-21, TC-22, TC-23 rewritten in tests.md); the Docker isolation scene extension is gone with the move (TC-23 became the live container check above), so follow-up F-2 is reduced to the platform's own older Docker scenes. F-1 (browser link check), F-3 (a day of digests) and F-5 (disable the two throwaway agents) stand. The CI job for `agents/` is a new follow-up (F-7).
