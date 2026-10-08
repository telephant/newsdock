# externalize-config — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-06)

| # | Check (command) | Result |
|---|---|---|
| 1 | AC → test: grep each `AC-n` in tests.md rows | pass: AC-1…AC-14 each have ≥ 1 TC; no TC without a valid AC |
| 2 | AC → design: grep AC ids in design.md §7 | pass: all 14 appear |
| 3 | AC → task: grep `Implements:` lines in tasks/ | pass: all 14 appear |
| 4 | TC → task: every TC id appears in some task | pass: TC-1…TC-26 |
| 5 | Names across docs: `kafka_topics_*`, `kafka.topics.*`, `heartbeat_max_age_seconds`, `newsdock_config`, file path | pass: identical in spec, design, detail, tests, tasks |
| 6 | Proposed ADRs: grep "Proposed" in ADR-0013/14/15 | pass: all Accepted 2026-10-06 |
| 7 | Open checklist items in design.md | pass: none |
| 8 | Glossary / tags / invented numbers | fixed: 4 terms added to spec glossary. Numbers (pool recycle 1800, 4/3 slack, heartbeat 120 s) come from today's values or are tagged **[assumption]** in design-detail |
| 9 | Scope leak from backlog.md | pass: no hot reload, schema, overlays, or tuning-as-config in any task |

Findings, open or accepted:
- **R-1 (medium, blocker for T-06):** M2a `dedup-syndication` is still `implement` with uncommitted edits to sink files; T-06 must wait for it to be committed. Other tasks do not touch those files.
- **R-2 (low, accepted):** agent container gets the whole config file read-only (ADR-0013 consequence; user accepted 2026-10-06).
- **R-3 (low, accepted):** TC-26 (log redaction) is mapped to AC-7 because the spec has no AC of its own for the effective-config log; it came from NFR §7 **[assumption]**.
- **R-4 (info):** the Next.js runtime-env claim is verified only from docs; T-01 proves it before T-11.
- **R-5 (info):** CI: T-12 may touch the workflow; per CLAUDE.md, push and read the run after touching `.github/`.

Go / no-go: **go** (R-1 only gates T-06).

## Order (walking skeleton, spike first)

**Spike first:** T-01 proves the least-verified claim (a standalone Next image reading config at start). If it fails, ADR-0014 needs a new option before any web work.

| Phase | Tasks | Proves | ACs | Effort |
|---|---|---|---|---|
| 0 Spike | T-01 | web runtime config works in the image | (AC-14 risk) | ~1 h |
| 1 Loader | T-02 | layered settings, errors, secrets, before-snapshot | AC-1,2,3,5,6,7 | ~0.5 day |
| 2 Skeleton | T-03 | one service end to end with the real file | AC-1…4, 9 | ~0.5 day |
| 3 Services | T-04, T-05, T-06, T-07, T-08 (T-04…T-08 independent after T-03; T-06 waits for M2a) | every Python tunable behind settings | AC-4, 8, 10, 11, 12 | ~2 days |
| 4 Wiring | T-09, T-10 | healthchecks and compose follow config | AC-13 | ~1 day |
| 5 Web | T-11 | runtime web config | AC-14 | ~0.5 day |
| 6 Guard + docs | T-12, T-13 | no literals creep back; docs match | AC-11 | ~0.5 day |

Efforts are rough guesses **[assumption]** for one person.

## Milestone markers

- **MS-1 after T-03:** AC-1, AC-2, AC-3, AC-4 (ingester), AC-9 pass; `NEWSDOCK_CONFIG_FILE=infra/config/newsdock.yaml` runs the ingester.
- **MS-2 after T-08:** every service reads the file; AC-8, AC-10, AC-11 (service parts), AC-12 pass.
- **MS-3 after T-10:** `make up` healthy with config-derived healthchecks; AC-13 passes.
- **MS-4 after T-13:** AC-14 manual check done, `make check` green; ready for `/spec-verify`.

## Definition of done (every task)

1. Tests written first and seen failing, then green (TCs named in the task).
2. `make check` green (plus the scoped `make test APP=…` / `make test-infra SCENE=…` the task names).
3. Docs/ADR updated where the task changes a documented fact (same edit, per CLAUDE.md).
4. No secrets in code, YAML, docs or logs.
5. `status.yaml` ACs moved to `in-progress`/`passing` with the TC that proves it.

## Progress

Tasks (dates 2026-10-07 unless noted):

- [x] T-01 spike (web runtime config) — **findings:** (a) yes: one `pnpm run build`, then two servers / two containers from one image showed different `apiBaseUrl` and `pollMs` in the SSR HTML and RSC payload, driven only by env and the mounted YAML at start. (b) Working code = async root layout with `await connection()` + `readFileSync` + `parse` (yaml) + client `ConfigProvider`; adopted in T-11. (c) The `yaml` package is bundled into the server chunk by Turbopack, so no tracing config was needed. (d) All routes become dynamic (`ƒ`), no prerender warnings; client components need a provider or a default in tests (T-11 chose a default context value).
- [x] T-02 `newsdock_config` package + before-snapshot (27 unit tests incl. load_settings)
- [x] T-03 ingester end to end + `infra/config/newsdock.yaml`
- [x] T-04 `newsdock_db` pool settings (`make_engine` takes `Settings` or a URL)
- [x] T-05 processor + Python topic job (`adapters/topics.py`)
- [x] T-06 sink (M2a was committed first as `95c3fa5`)
- [x] T-07 API (`ServiceLimits` in `domain/service.py`)
- [x] T-08 agent (isolation tests TC-18/19 plus the M1 TC-35 kept)
- [x] T-09 heartbeat max age + per-app `healthcheck` modules
- [x] T-10 compose wiring (config mount, `x-db-env` anchor, topic job on the processor image, new healthchecks, `API_PORT`/`WEB_PORT`); `create-topics.sh` removed
- [x] T-11 web runtime config (`lib/config/runtime.ts`, `ConfigProvider`, api helpers take the base URL); manual check TC-25 pending
- [x] T-12 `infra/scripts/check_config.py` + `make config-python` + rule tests
- [x] T-13 docs (CLAUDE.md Configuration section, README, app READMEs, roadmap M2b, superseded notes in the M0/M1 design docs)

Deviations from the design, recorded:
- `heartbeat_max_age_seconds` fields were added in T-03/T-05/T-06/T-08 (with their defaults tests) instead of T-09, so each app's config was touched once; T-09 added the writers and healthcheck modules.
- `newsdock_db.Settings` keeps `DATABASE_URL` but also accepts `NEWSDOCK_DATABASE_URL`; `make_engine` accepts a bare URL to keep existing integration tests unchanged.
- `uvicorn_workers > 1` runs the app by import string (`create_app` factory).

Verification so far (2026-10-07): `make check` green (269 Python tests, 13 web tests, lint, mypy, import-linter, layout, config check, docs); `make test-infra` 55/55 after fixing one stale M2a assertion (migration head `0003` in `test_stack.py`); `make test-rules-python` 18 passed; TC-25 manual check passed (see status.yaml). Not run: CI on GitHub (`.github/` untouched, nothing pushed).
