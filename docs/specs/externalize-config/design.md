# externalize-config — Design (Milestone 2b)

Status: **approved** · 2026-10-06 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (each diagram has a "Check" box) → ADR-0013, ADR-0014, ADR-0015 (Accepted) in `../../adr/` → answer the checklist at the bottom.

## 1. Components (ids continue the M1/M2a numbering; apps C-1…C-8 keep their ids)

| Id | Component | Change | Notes |
|---|---|---|---|
| C-11 | `newsdock_config` (`packages/config`) | **new** | `LayeredSettings` base class: sources env → YAML file → defaults; `common` + service-section merge; secret-key and unknown-key rejection; health helpers (C-13). Imports no app; no app domain imports it |
| C-12 | `infra/config/newsdock.yaml` | **new** | The one committed, secret-free file: `common:` plus `ingester`, `processor`, `sink`, `api`, `agent`, `web` sections |
| C-1…C-4, C-6, C-7 | Ingester, processor, sink, API, agent | **changed** | Each `config.py` extends `LayeredSettings` and gains the fields of the §3 inventory; each `__main__` passes settings into adapters and domain constructors (no more ctor-default literals) |
| C-5 | `newsdock_db` | **changed** | `Settings` gains pool fields (`pool_size`, `max_overflow`, `pool_recycle_seconds`, `pool_pre_ping`); `DATABASE_URL` stays env-only |
| C-13 | Heartbeat + health CLI (in C-11) | **new** | Worker writes its own allowed age into the heartbeat file; `python -m newsdock_<app>.adapters.healthcheck` compares file age to that value. Replaces the `find -mmin -N` literals |
| C-14 | Topic job (`newsdock_processor.adapters.topics`) | **changed** | Python replacement for `create-topics.sh`: creates the configured topics idempotently with configured partitions/replication |
| C-15 | Web runtime config (C-8) | **changed** | Root layout reads `web` config per request (env > file) and hands it to client components via a provider; replaces build-time `NEXT_PUBLIC_API_BASE` |
| C-16 | Config check (`infra/scripts/check_config.py`) | **new** | In `make check`: file keys known to some service, no secret keys, no tunable literals outside `config.py` (AC-11) |

## 2. Key flows

- **F-8 Resolve settings (startup):** service builds `Settings()` → env value wins → else file (`common` merged under the service section, nested keys flattened to field names) → else code default → validators (poll floor 900 s) → effective config logged, secrets redacted. (Diagram 2)
- **F-9 Heartbeat:** worker loop → `touch(path, max_age_seconds)` → compose healthcheck runs the app's `healthcheck` module → exit 0 only if file age ≤ stored max age. (Diagram 3)
- **F-10 Web boot:** web server starts → layout calls `connection()` then `getRuntimeConfig()` (env > YAML) → `ConfigProvider` → `API_BASE`, `POLL_MS` in the browser. (Diagram 4)
- **F-11 Stack start:** `make up` → `topics` job reads the file, creates topics → apps start with the file mounted read-only and `NEWSDOCK_CONFIG_FILE` set. (Diagram 1)

## 3. Contracts

**File shape** (nested keys flatten with `_` to the field name; e.g. `kafka.topics.clean` → `kafka_topics_clean`, env `NEWSDOCK_KAFKA_TOPICS_CLEAN`):

```yaml
common:   {log_level: INFO, heartbeat_file: /tmp/healthy, kafka: {bootstrap_servers: kafka:9092, topics: {raw: gkg.raw, clean: gkg.clean, dlq: gkg.dlq}}}
ingester: {poll_interval_seconds: 900, max_attempts: 4, http_timeout_seconds: 60}
sink:     {retention_days: 7, story_window_hours: 48, batch_size: 200}
```

**Resolution rules**

| Rule | Behaviour |
|---|---|
| Order | init args → env → file → default (AC-3) |
| Inheritance | key in service section beats same key in `common` (AC-2) |
| `common` key unknown to a service | skipped for that service (the agent never sees `kafka_*`, AC-12); the check in C-16 fails if no service knows it |
| Key unknown in a service section | startup error naming `section.key` (AC-6) |
| Secret-looking key (name contains `password`, `passwd`, `secret`, `token`, `dsn`, `credential`, `api_key` or is `database_url`) anywhere in the file | startup error naming the key (AC-7) |
| `NEWSDOCK_CONFIG_FILE` set but file missing or unparsable | exit non-zero naming the path (AC-5); unset → file layer skipped (AC-4) |
| Env names | unchanged: `NEWSDOCK_<FIELD>`, agent `NEWSDOCK_AGENT_<FIELD>`, and the aliases `KAFKA_BOOTSTRAP_SERVERS`, `MCP_URL`, `OLLAMA_URL`, `DATABASE_URL` |

**Heartbeat file:** content is the integer `max_age_seconds`; mtime is the last beat. Default max age: ingester `ceil(4/3 × poll_interval)` (= today's 20 min at 900 s), agent `2 × loop_interval`, processor and sink 120 s (today's values).

## 4. Tricky parts

1. **Two keys for one field.** Aliased fields (`KAFKA_BOOTSTRAP_SERVERS`) otherwise get both an env key and a file key and pydantic rejects the pair as "extra". Spike (2026-10-06): the file source skips any field that env already supplies, and models set `populate_by_name=True`. **[verified]**
2. **Poll floor.** The 900 s validator runs after merging, so a file value of 60 becomes 900 (AC-9).
3. **Agent isolation.** The agent loads `common` filtered to its own fields plus its section; its model has no kafka/database fields and `extra="forbid"`, so a `kafka_*` key in `agent:` fails. Network isolation (AC-13 of M1) is unchanged. The whole file is mounted in the agent container (ADR-0013 risk).
4. **Compose cannot read YAML.** So nothing in compose depends on a file value: healthchecks run app code, host ports stay in `.env`, the DB URL anchor is compose-native.
5. **Invariants stay in code.** Manual offset commits and `follow_redirects=True` are CLAUDE.md rules, not tunables; a config key could only break them.

## 5. Top failure modes

| Failure | Result |
|---|---|
| Typo in a service key | Startup error naming the key; service never half-starts |
| File mounted but env path wrong | Exit non-zero, path in message (AC-5) |
| Poll interval raised, heartbeat age not | Cannot happen: the worker writes its own max age |
| Web env missing | Falls back to file, then to today's default `http://127.0.0.1:8000` |
| Secret pasted into the file | Startup error; the file is committed so this is also caught by C-16 in CI |

## 6. Technology

pydantic-settings 2.15 custom source + PyYAML 6 (both already installed **[verified]**); Python `confluent_kafka` AdminClient for topics (already a dependency of processor and sink); Next 16 `connection()` + server-to-client props, `yaml` npm package for the web file read (docs: Next "Environment Variables" and "Self-Hosting" guides **[verified]**; confirmed by the T-01 spike and the built-image check 2026-10-07 **[verified]**). No new service, no new infrastructure.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1, AC-2, AC-3, AC-4 | C-11 resolution, F-8; C-12 |
| AC-5, AC-6, AC-7 | C-11 error paths, F-8 |
| AC-8 | C-1/C-3/C-4 topic fields, C-14 |
| AC-9, AC-10 | C-1 `max_attempts`, C-4 `retention_days`, F-8 |
| AC-11 | C-16 |
| AC-12 | C-11 section filtering, C-7 model |
| AC-13 | C-13, F-9 |
| AC-14 | C-15, F-10 |

## 8. Questions to answer before approving this design

- [x] Confirm D-8: topic names leave CLAUDE.md "Fixed names" and become config (defaults unchanged).
- [x] The file lives at `infra/config/newsdock.yaml` (no new repo-root folder, no ADR for DR-1). OK?
- [x] New package `packages/config` (ADR-0013) rather than putting the loader in `newsdock_core` (which must stay I/O-free). OK?
- [x] Mount the whole file in the agent container (simple) vs a generated agent-only slice (stricter AC-13)? Recommended: whole file; the agent model exposes no other fields.
- [x] Manual offset commits and `follow_redirects` stay in code (deviation from the spec §3 list). OK?
- [x] Host ports stay in `.env`, container ports fixed (AC-13/14 revised). OK?
- [x] Healthchecks become app code (`healthcheck` module per app) instead of shell `find`. OK?
- [x] Web reads the YAML itself (adds the `yaml` npm package) rather than env only. OK?
