# externalize-config — Verification

Verified 2026-10-07 by running everything in this session (no result carried over). **Verdict: pass with follow-ups.**

## Runs

| Run | Result |
|---|---|
| `make check` (ruff, ruff format, mypy strict over 149 files, import-linter 4 contracts, layout, config check, 269 Python tests, web lint/format/typecheck/13 vitest tests, docs check) | pass |
| `make test-infra` (every Docker scene: db, kafka, sink, api, pipeline, e2e, stack, images) | 55 passed, 214 s |
| `make test-rules-python` | 18 passed |
| `pnpm run build` for the web app | pass; all routes dynamic (`ƒ`) |

## Acceptance criteria

| AC | TCs | Result | Evidence |
|---|---|---|---|
| AC-1 file value used | TC-1 | pass | `packages/config/tests/unit/test_settings.py`, `apps/ingester/tests/unit/test_config.py`; in-image: ingester read 1800 from a mounted file |
| AC-2 common inherited / overridable | TC-2 | pass | same files; in-image: `common.log_level: DEBUG` reached ingester and agent |
| AC-3 env beats file (incl. aliased) | TC-3 | pass | `KAFKA_BOOTSTRAP_SERVERS` and `NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS` over file |
| AC-4 no file, same defaults | TC-4 | pass | per-app tests against `config_defaults_before.json` (taken before any change) + inventory defaults; `check_config` proves committed file equals defaults |
| AC-5 file path configurable, fail fast | TC-5 | pass | unit + in-image: `NEWSDOCK_CONFIG_FILE=/nope.yaml` → `config error: ... /nope.yaml`, exit 2 |
| AC-6 unknown keys rejected | TC-6 | pass | names `svc.batchsize`; `check_config` covers `common` keys |
| AC-7 secrets rejected in file | TC-7, TC-26 | pass | 6 key names × 2 locations; `DATABASE_URL` still from env; effective-config log masks secret names |
| AC-8 topic names from one setting | TC-8, TC-9, TC-10 | pass | route, ingester publisher, sink loop/DLQ use settings; topic job created `test.*` topics on a real broker twice |
| AC-9 ingester retry limit / timeouts / floor | TC-11, TC-12 | pass | `max_attempts=2` fails slot on 2nd miss; file value 60 → 900 |
| AC-10 retention days | TC-13 | pass | cutoff = now − 3 days; default 7 |
| AC-11 no tunable literals | TC-14…TC-17 | pass | `check_config` clean on the tree; rule test fails when `"gkg.clean"` or `MAX_ATTEMPTS` is reintroduced; API limits, agent limits, DB pool tests |
| AC-12 agent stays isolated | TC-18, TC-19 | pass | agent loads a file with `common.kafka`, no kafka/database field; `kafka_*`/`database_*` in `agent:` fails; agent image has no `confluent_kafka`, `psycopg`, `sqlalchemy`, `newsdock_db`; e2e isolation scene passed |
| AC-13 healthcheck follows config | TC-20, TC-21, TC-22 | pass | 25 min vs 45 min against max age 2400; ingester 1800 → 2400 in image; all services `healthy` in the stack scene |
| AC-14 web follows runtime config (manual) | TC-23, TC-24, TC-25 | manual-ok | one built image (`newsdock-web:dev`), two containers: file only → `http://127.0.0.1:8000`, 60000 ms; env → `http://localhost:9999`, 7000 ms; image id unchanged |

## Measurements

| What | Result |
|---|---|
| Healthcheck run (`python -m newsdock_ingester.adapters.healthcheck`) | ≈ 240 ms inside the container (avg of 5); ≈ 390 ms via `docker run`. Limit in compose is 5 s, so no concern |

## Extra checks beyond the plan

- Multi-worker API (`NEWSDOCK_UVICORN_WORKERS=2`): two application processes started and `/api/health` returned 200 (manual, no automated test).
- Image contents: sink, API, agent and ingester images load their mounted file and report effective values.

## Doc drift

| Finding | State |
|---|---|
| design-detail said `uvicorn_log_level` defaults to `log_level`; code default is `"info"` | fixed |
| design.md listed a shorter secret-name pattern than the code | fixed |
| ADR-0014 / design.md still called the Next.js runtime claim unconfirmed | fixed (confirmed by T-01 and the image check) |
| `test_stack.py` expected migration head `0002` (stale since M2a added `0003`) | fixed in T-10 |
| Topic names / `create-topics.sh` / `find -mmin` in M0–M1 specs | noted with a dated "superseded in part" line; history kept |
| `grep` for `create-topics`, `NEXT_PUBLIC_API_BASE`, `mmin` in live code and docs | no stale references |
| Design field inventory vs real `Settings` classes (scripted) | 0 missing |

## Scope

Nothing implemented outside the spec except two small conveniences, both inside the inventory's intent: `NEWSDOCK_DATABASE_URL` accepted as an alias of `DATABASE_URL`, and `make_engine` accepting a bare URL. Nothing from `backlog.md` leaked in (no hot reload, no schema publication, no overlays).

## Follow-ups (accepted, moved to backlog.md)

1. **CI path filter misses `infra/config/**`** (and `infra/compose.yaml`): editing only `newsdock.yaml` does not trigger the job that validates it. Fixing it touches `.github/`, so per CLAUDE.md push and read the run. CI has also not yet run on this branch.
2. **Multi-worker API path has no automated test.**
3. **Whole config file is mounted in the agent container** (accepted risk R-2; names only, no credentials).
4. **Dedup-syndication (M2a) is still unverified** (`/spec-verify dedup-syndication`); this feature builds on it.
