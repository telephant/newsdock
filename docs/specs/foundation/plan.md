# foundation — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-05)

| # | Check | Command / method | Result |
|---|---|---|---|
| 1 | AC → test coverage | grep AC column of `tests.md` for AC-1…AC-17 | **pass**: every AC has ≥ 1 TC (counts: AC-1 3, AC-2 1, AC-3 2, AC-4 3, AC-5 1, AC-6 3, AC-7 2, AC-8 3, AC-9 4, AC-10 3, AC-11 3, AC-12 2, AC-13 2, AC-14 3, AC-15 1, AC-16 5, AC-17 3); 44 TCs, no orphans |
| 2 | AC → design coverage | grep `design.md` §7 table | **pass**: 17 of 17 |
| 3 | AC → task coverage | grep `Implements:` lines in `tasks/` | **pass**: each AC has ≥ 1 task; every TC is named in a task |
| 4 | Cross-doc names | grep make targets, `newsdock_db`, `packages/db`, ADR numbers across spec, design, diagrams, tests, tasks | **pass** after fixes (below) |
| 5 | Proposed ADRs treated as decided | grep `Proposed` in `docs/adr/` and foundation docs | **pass**: none Proposed (ADR-0005…0010 Accepted) |
| 6 | Untagged claims, invented numbers, glossary | grep numbers in spec ACs; review new terms | **pass** after adding "Compose profile" and "Rule test" to the glossary; no invented number is a requirement |
| 7 | Scope leaks from `backlog.md` | grep backlog items in tasks | **pass**: backlog items appear only under "Out of scope" |
| 8 | Open questions and checklist items | grep `- [ ]` in spec and design | **pass**: none open |

**Findings fixed during planning:** (F-1) `research.md` at the repo root would fail DR-1, so the user decided to move it to `docs/research.md` (done in T-05, 5 references listed); (F-2) design diagram 6 question answered: `make down` keeps volumes (recorded in design-detail §6, tested by TC-22); (F-3) design.md Make-target table lacked `setup-python`, `setup-web`, `test-rules`, `test-infra` (added); (F-4) two glossary terms added.

**Open, non-blocking:** (O-1) the M1 docs are stale for M0's decisions: `mvp/design-detail.md` §8 says tooling is chosen in the plan, lists only `packages/core` (no `packages/db`), never names SQLAlchemy Core versus ORM, and two of its Design TODOs (migrations, compose startup order) are now covered by M0. Update them in `/spec-design mvp` before `/spec-plan mvp`. (O-2) AC-2, AC-12, AC-13, AC-15 are manual and need the owner's machine and a pushed GitHub repo (`/spec-verify`). (O-3) T-05 uses a transitional `PENDING_UNTIL` table in `check_layout.py` so DR-3 can pass before Dockerfiles and READMEs exist; T-08 and T-12 must delete their entries.

**Verdict: GO.** `gates.plan: approved`. No design review file exists for this feature, so nothing to retire.

## Spike first

**T-01 Docker spike** is first because every Docker claim (Kafka healthcheck, `up --wait`, one-shot jobs, `uv sync --frozen --package` with a partial copy, Docker Desktop on this macOS) was unverified at design time and invalidates T-08…T-11 if wrong. **T-02 web spike** (Node pin through pnpm, Next 16.3.8 with TypeScript 7) can run in parallel. Both need T-00 (owner installs).

## Task order (walking skeleton)

Effort is relative (S/M/L), no dates **[assumption]**.

| Phase | Task | Title | Depends on | Effort | ACs |
|---|---|---|---|---|---|
| 0 Prerequisites and spikes | [x] T-00 (2026-10-05; Ollama model pull and docs commit deferred to the owner, needed before AC-2 and T-03) | Owner prerequisites (no code) | none | S | enables AC-2, 8–11, 15 |
| | [x] T-01 (2026-10-05) | SPIKE: Docker, Kafka, Postgres, uv-in-Docker | T-00 | M | de-risks AC-8–11 |
| | [x] T-02 (2026-10-05) | SPIKE: web toolchain and Node pin | T-00 | S | de-risks AC-3, 4, 6 |
| 1 Python skeleton and gate | [x] T-03 (2026-10-05) | Python workspace skeleton, `make test` | T-00 | M | AC-3, AC-6 (Python) |
| | [x] T-04 (2026-10-05) | Python quality gate and rule tests | T-03 | L | AC-4 (Python), AC-5, AC-7, AC-17 |
| | [x] T-05 (2026-10-05) | Layout check script, move `research.md` | T-04 | M | AC-16 |
| | [x] T-06 (2026-10-05) | `make doctor` | T-03 | S | AC-1, AC-2 |
| 2 Web | [x] T-07 (2026-10-05) | Web scaffold and gate | T-02, T-03 | M | AC-3, AC-4, AC-6 (web) |
| 3 Images and infra | [x] T-08 (2026-10-05) | App Dockerfiles, `apps` profile, `make build` | T-01, T-03, T-07 | L | AC-8 |
| | [x] T-09 (2026-10-05) | Compose Kafka + Postgres, `up`/`down` | T-01, T-03 | M | AC-9 |
| | [x] T-10 (2026-10-05) | Topic setup job | T-09 | S | AC-10 |
| | [x] T-11 (2026-10-05) | `packages/db`, Alembic, `make migrate` | T-09, T-03 | L | AC-11 |
| 4 Docs, CI, onboarding | [x] T-12 (2026-10-05) | Docs, `docs-check`, full `make check` | T-05, T-07, T-11 | M | AC-14, AC-15 (README) |
| | [x] T-13 (2026-10-05) | CI workflow | T-04, T-07, T-08, T-11, T-12 | M | AC-12, AC-13 |
| | [x] T-14 (2026-10-05) | Clean-clone dry run, CLAUDE.md commands | T-00…T-13 | S | AC-15, AC-2 (dry runs) |

## Milestone markers

| Marker | After | ACs reachable | Observable |
|---|---|---|---|
| A Python gate green | T-06 | AC-1, AC-3/4/6 (Python), AC-5, AC-7, AC-16, AC-17 | `make check-python` and `make test-rules` pass; layout and import rules fail when broken |
| B Web in the gate | T-07 | AC-3, AC-4, AC-6 complete | `make setup` and `make check` (Python + web) pass |
| C Infra runs | T-11 | AC-8, AC-9, AC-10, AC-11 | `make build`, then `make up` shows Kafka and Postgres healthy, 3 topics, migration `0001` |
| D Ready to verify | T-14 | AC-12, AC-13, AC-14, AC-15 (dry run) | CI workflow in place, README-only dry run green; then `/spec-verify foundation` |

A multi-part AC (AC-3, AC-4, AC-6) is marked `passing` only after its last part lands (T-07 for AC-3/AC-6; T-12 for AC-4).

## Definition of Done (every task)

- Tests written first and seen failing for the right reason; then green.
- The project check command is green for what exists (`make check`; also `make test-rules` or `make test-infra` when the task touched them).
- Docs and ADRs touched by the change are updated (design-detail findings, README, `CLAUDE.md`); a contradiction between reality and the design stops the task for an AskUserQuestion.
- No secrets: `.env` stays git-ignored, `.env.example` holds placeholders only, images contain no `.env`.
- An AC is marked `passing` in `status.yaml` only after its named test passed in that session.
- No commit unless the owner asks.

## Out of scope for M0 (stay in `backlog.md`)
OpenAPI type generation, running services with healthchecks, pre-commit hooks, dependency bots, secret and image scanning, CI caching, dev containers, Linux/Windows notes, any M1 domain code.

## Implementation notes (T-14 dry run, 2026-10-05)

Dry run in a clean copy (tracked plus untracked-not-ignored files only, no `.venv` or `node_modules`), following only `README.md`: `make doctor`, `make setup`, `make check` (86 Python tests, web, docs; about 24 s with warm caches), `make build` (7 images, about 11 s warm), `cp .env.example .env`, `make up` (about 12 s: Kafka and Postgres healthy, 3 topics, revision `0001`, `vector`), `make down`, `make up` again. Stumbling point found and fixed: raw `docker compose` needs `--env-file .env` (README troubleshooting and `CLAUDE.md`). Image sizes: Python apps 229 MB, web 402 MB. These are dry-run numbers for the measurements table, not the formal evidence.

**Left for `/spec-verify`:** TC-4 (AC-2, needs an Ollama model pulled), TC-31 and TC-32 (AC-12, AC-13: push the branch and open pull requests that change only `apps/web` and only `apps/api`, plus one touching `packages/core`), TC-36 (AC-15 on a real clone of a pushed commit), measurements M-1…M-4, and a re-run of `make check`, `make test-rules` and `make test-infra`.

**TC-4 dry-run evidence (owner's terminal, 2026-10-05):** `make doctor` exited with all tools present and printed: Docker 29.8.1, Compose v5.5.1, uv 0.12.23, pnpm 12.9.1, Python 3.12.14 (resolved by uv), Node 24.x (pinned by pnpm devEngines), `ollama: models: llama3.2:1b`. The owner ran it; `/spec-verify` repeats it for the formal record.
