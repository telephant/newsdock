# what-happen — Plan

## Plan validation

Run 2026-10-30 after writing tests and tasks (commands in the right column were run, not eyeballed).

| # | Check | Result |
|---|---|---|
| 1 | Every AC-1…AC-16 appears in `tests.md` (`grep` per AC); every TC names an AC | pass |
| 2 | Every AC maps to a component in `design.md` §7 | pass |
| 3 | Every AC appears in the `Implements:` line of at least one task | pass |
| 4 | Names agree across docs: `digest_*` settings, `C-50…C-58`, `F-40/F-41`, file names, `NEWSDOCK_DIGEST_API_KEY` | pass |
| 5 | No Proposed ADR treated as decided (ADR-0028 is Accepted) | pass |
| 6 | Nothing from `backlog.md` in the tasks (no UI page, no label table, no region filter) | pass |
| 7 | Open questions and unchecked checklist items | none open; design checklist resolved by delegation (user asked to finish the pipeline), listed in `design.md` §8 for review |

Findings fixed while planning: D-1 text no longer says "no ADR"; D-7 carries the share-based refinement; the layout rule for a root `digests/` folder is an open risk handled in T-10 (see risks).

Risks carried into implementation:

- R-1 (closed 2026-10-30) A root `digests/` folder is rejected by `check_layout.py` (DR-1); the output lives in `infra/digests/` (spike §4).
- R-2 (closed 2026-10-30) The live stack was running; T-01 used real data (spike.md).
- R-5 (medium, open) Theme groups are only loosely coherent (spike §2.5), so model lines may be vague. Accepted for a test harness; T-11 judges it on a warm baseline; story clustering is in the backlog. The user chose the shape (D-3), so this is flagged in the final report.
- R-3 (low) A 3B model may produce poor sentences. Accepted by the spec (D-5, D-9); T-01 only picks the better of two.
- R-4 (low) Shared `Settings` class: new fields must not change the scoring loop's behaviour. TC-21 and the existing `test_config.py` guard this.

## Walking skeleton and order

Spike first: **T-01** de-risks the biggest unverified claims (articles per hour, how noisy the themes are, which model writes usable lines, and that the layout rules accept the output folder). Everything later depends on those numbers only through settings defaults, so the pure code can start straight after.

| Phase | Tasks | ACs reached | Effort |
|---|---|---|---|
| 0 Spike | T-01 | measurements, fixture | 0.5 day |
| 1 Settings | T-02 | AC-15 (settings half) | 0.25 day |
| 2 Pure domain | T-03 themes + baseline, T-04 stories, T-05 render + prompt | AC-4, AC-5 (logic), AC-6, AC-7, AC-8, AC-9, AC-14 (logic) | 1 day |
| 3 Adapters | T-06 files + MCP paging, T-07 summariser | AC-1 (client), AC-5 (corrupt file), AC-12, AC-14, AC-10 (adapter) | 0.75 day |
| 4 Cycle and loop | T-08 `DigestCycle`, T-09 entry and loop | AC-1, AC-2, AC-3, AC-10, AC-11, AC-13 | 0.75 day |
| 5 Ship | T-10 compose, Makefile, docs, isolation | AC-15 | 0.5 day |
| 6 Live | T-11 live run and closing | AC-16 | 0.5 day |

Milestones: after phase 2 the digest text can be rendered from fake data; after phase 4 `make digest-once` logic works against fakes; after T-10 the service starts under compose; T-11 proves it on real data.

## Task list

| Task | Title | Implements | Depends on |
|---|---|---|---|
| [T-01](tasks/T-01.md) | Spike: measure real data, pick the model, check the output folder — **done 2026-10-30** ([spike.md](spike.md)) | (measurements) | none |
| [T-02](tasks/T-02.md) | `digest_*` settings and config rows — **done 2026-10-30** | AC-15 | T-01 |
| [T-03](tasks/T-03.md) | Theme counting, ranking and the baseline model — **done 2026-10-30** | AC-4, AC-5, AC-14 | T-02 |
| [T-04](tasks/T-04.md) | Story picker — **done 2026-10-30** | AC-6 | T-03 |
| [T-05](tasks/T-05.md) | Markdown renderer and prompt builder — **done 2026-10-30** | AC-7, AC-8, AC-9 | T-04 |
| [T-06](tasks/T-06.md) | File adapters and MCP paging — **done 2026-10-30** | AC-1, AC-5, AC-12, AC-14 | T-03, T-05 |
| [T-07](tasks/T-07.md) | Ollama summariser adapter — **done 2026-10-30** | AC-10 | T-05 |
| [T-08](tasks/T-08.md) | `DigestCycle` — **done 2026-10-30** | AC-1, AC-2, AC-3, AC-10, AC-11 | T-06, T-07 |
| [T-09](tasks/T-09.md) | Digest entry, hourly loop, heartbeat, `--once` — **done 2026-10-30** | AC-13 | T-08 |
| [T-10](tasks/T-10.md) | Compose service, Makefile, README, isolation test, docs — **done 2026-10-30** (TC-23, the Docker scene, is written but not run: the dev stack holds its ports; run `make test-infra SCENE=e2e` with the stack stopped) | AC-15 | T-09 |
| [T-11](tasks/T-11.md) | Live run and closing checks — **done 2026-10-30** (one checklist item is the owner's: five links in a browser; the warm-baseline look needs hours of running) | AC-16 | T-10 |

## Definition of Done (every task)

1. Its tests were written first and now pass.
2. `make check` is green (ruff, mypy strict, import-linter, layout, config, docs).
3. Docs that repeat a changed fact are updated in the same commit (names, settings, statuses); ADR-0028 stays accurate.
4. No secrets in code, docs or `.env.example` values.
5. `status.yaml` ACs updated (`in-progress` / `passing`).
6. One commit per task: `feat(agent): T-NN <title>` (or `spec(what-happen): T-01 ...` for the spike).
