# externalize-config — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. Loader (`newsdock_config`)

```
packages/config/src/newsdock_config/
  settings.py   LayeredSettings(BaseSettings): populate_by_name, extra="forbid",
                class var `section`; settings_customise_sources = (init, env, FileSource)
  source.py     FileSource: load yaml -> flatten(common) filtered to model fields
                + flatten(section) strict -> drop fields env already supplies
  secrets.py    SECRET_KEY_PATTERN, check_no_secrets(raw)
  health.py     write_heartbeat(path, max_age), check_heartbeat(path) -> exit code
```

- `flatten({kafka: {topics: {clean: x}}})` → `{"kafka_topics_clean": "x"}`. A key whose flattened name collides with a real field name wins by name; lists and scalars are leaves.
- A service section key that is not a model field → `ConfigError("sink.batchsize is not a setting of sink")`; surfaced instead of pydantic's raw "extra inputs" text.
- `env_prefix` stays per app (`NEWSDOCK_`, agent `NEWSDOCK_AGENT_`); `section` class var picks the YAML section.
- "Field supplied by env" = prefix+name or any `AliasChoices` choice present in `os.environ` (case-insensitive). Verified in a scratch spike: file-only, inheritance, env beats file incl. aliased `KAFKA_BOOTSTRAP_SERVERS`, unknown-key rejection. **[verified]**
- Agent `extra="forbid"` plus its env prefix keep TC-35 (unknown `NEWSDOCK_AGENT_*` fails): the env source is unchanged.
- Effective-config log: `Settings.redacted()` returns field values with any name matching the secret pattern replaced by `***`; each `__main__` logs it once at INFO.
- Import rules (import-linter): `newsdock_config` may import `pydantic`, `pydantic_settings`, `yaml`, stdlib; may not import any app, `newsdock_core` or `newsdock_db`. `newsdock_db.config` extends `LayeredSettings` (db → config allowed; `newsdock_core` → config stays forbidden). `domain/` packages may not import it (DR-6 stays: only `config.py`/`__main__`/adapters do).

## 2. Field inventory (default = today's value, so AC-4 holds)

Section = where the key lives in the YAML; "common" keys are inherited by every service that declares the field.

| Section | Key (field name) | Default | Replaces |
|---|---|---|---|
| common | `log_level` | INFO | per-app default |
| common | `heartbeat_file` | /tmp/healthy | per-app default |
| common | `kafka.bootstrap_servers` | 127.0.0.1:29092 | per-app default; compose env `kafka:9092` stays as env override |
| common | `kafka.topics.raw / clean / dlq` | gkg.raw / gkg.clean / gkg.dlq | 6 literals incl. `create-topics.sh` |
| common | `database.pool_size / max_overflow / pool_recycle_seconds / pool_pre_ping` | 5 / 10 / 1800 / true | `make_engine` (pool numbers are SQLAlchemy's defaults except recycle, **[assumption]** 1800) |
| ingester | `poll_interval_seconds` (floor 900) | 900 | existing |
| ingester | `gdelt_base_url` | http://data.gdeltproject.org/gdeltv2 | existing |
| ingester | `gdelt_index_path` | /lastupdate.txt | `adapters/gdelt.py` |
| ingester | `http_timeout_seconds` | 60 | ctor default |
| ingester | `max_attempts` | 4 | `MAX_ATTEMPTS` |
| ingester | `heartbeat_max_age_seconds` | ceil(4/3 × poll) | compose `-mmin -20` |
| processor | `kafka.group_id` | processor | ctor default |
| processor | `kafka.auto_offset_reset` | earliest | inline |
| processor | `kafka.topic_partitions / topic_replication_factor` | 1 / 1 | `create-topics.sh` |
| processor | `batch_size`, `poll_timeout_seconds` | 200, 1.0 | existing |
| processor | `heartbeat_max_age_seconds` | 120 | compose |
| sink | `kafka.group_id`, `kafka.auto_offset_reset` | sink, earliest | ctor default / inline |
| sink | `batch_size`, `batch_window_seconds`, `db_backoff_seconds` | 200, 1.0, 5.0 | existing |
| sink | `retention_days` | 7 | `RETENTION_DAYS` |
| sink | `retention_interval_seconds` | 3600 | existing |
| sink | `story_window_hours` | 48 | existing; `DEFAULT_WINDOW` literal removed (domain gets the value as a parameter, no default) |
| sink | `heartbeat_max_age_seconds` | 120 | compose |
| api | `host`, `port` | 0.0.0.0, 8000 | existing |
| api | `mcp_allowed_hosts`, `cors_origins` | as today | existing |
| api | `cors_allow_methods`, `cors_allow_headers` | GET, * | `adapters/http.py` |
| api | `first_run_window_minutes` | 60 | `FIRST_RUN_WINDOW` |
| api | `max_payload_bytes` | 65536 | `MAX_PAYLOAD_BYTES` (error message built from it) |
| api | `search_page_default / search_page_max` | 20 / 100 | `service.py` |
| api | `list_new_page_default / list_new_page_max` | 50 / 200 | `service.py` |
| api | `kafka_probe_timeout_seconds` | 1.0 | `kafka_health.py` |
| api | `uvicorn_workers`, `uvicorn_log_level` | 1, info | `uvicorn.run` defaults (workers > 1 starts the app from an import string) |
| agent | `mcp_url`, `ollama_url`, `model`, `agent_name`, `theme_prefixes`, `cursor_file`, `loop_interval_seconds` | as today | existing |
| agent | `batch_limit` | 200 | `loop.py` ctor |
| agent | `ollama_timeout_seconds`, `ollama_temperature` | 120, 0 | `adapters/ollama.py` |
| agent | `eval_threshold` | 0.5 | `DEFAULT_THRESHOLD` (CLI `--threshold` still wins) |
| agent | `export_limit`, `export_timeout_seconds` | 100, 30 | `export_labels.py` |
| agent | `heartbeat_max_age_seconds` | 2 × loop interval | compose |
| web | `api_base_url` | http://127.0.0.1:8000 | `NEXT_PUBLIC_API_BASE` |
| web | `poll_ms`, `page_size` | 60000, unset (server default) | `Feed.tsx` `POLL_MS`; `limit` param |

**Stays in code (D-7 and invariants):** `enable.auto.commit=False`, `follow_redirects=True`, `stream=False`, API route prefixes, dead-letter reasons, status literals, story-key constants, agent prompt and `OUTPUT_SCHEMA`, `GKG_COLUMN_COUNT`, `MAX_DLQ_LINE_CHARS`, MCP server name, UI copy.

**Agent model** declares none of `kafka_*`, `database_*`, `retention_*`; `extra="forbid"` rejects them in `agent:` (AC-12). Common keys it does not declare are skipped.

## 3. Compose and runtime wiring

- `x-app-env` / `x-db-env` extension anchors replace the DB URL repeated 4× (migrate, ingester, sink, api). The URL itself still comes from `.env` (secret).
- Each Python app service gets `volumes: ./config:/etc/newsdock:ro` and `NEWSDOCK_CONFIG_FILE: /etc/newsdock/newsdock.yaml`. `topics` uses the processor image with command `python -m newsdock_processor.adapters.topics` (needs the file and `kafka_bootstrap_servers`, via the same env override `KAFKA_BOOTSTRAP_SERVERS: kafka:9092`).
- Env that compose keeps setting (topology, not tuning): `KAFKA_BOOTSTRAP_SERVERS: kafka:9092`, `DATABASE_URL`, agent `MCP_URL=http://api:8000/mcp`, `OLLAMA_URL=http://host.docker.internal:11434`. They stay in compose because they are service-discovery names that differ from the host-run defaults in the file.
- Healthchecks: `python -m newsdock_<app>.adapters.healthcheck` (ingester, processor, sink, agent: heartbeat age; api: GET `/api/health` on its configured port). Web: `node -e "fetch('http://localhost:'+process.env.PORT)..."`. Docker-level `interval/timeout/retries/start_period` stay in compose (they are Docker scheduling, not app tunables).
- Ports: container-internal fixed (api 8000, web 3000, kafka 9092/29092); host mappings `127.0.0.1:${API_PORT:-8000}:8000`, `${WEB_PORT:-3000}:3000`, existing `POSTGRES_PORT`. `.env.example` gains `API_PORT`, `WEB_PORT`.

## 4. Web runtime config (ADR-0014)

- `src/lib/config/runtime.ts` (server-only): reads `NEWSDOCK_CONFIG_FILE` (YAML via `yaml`), merges `common`→`web`, env `NEWSDOCK_WEB_API_BASE_URL`, `NEWSDOCK_WEB_POLL_MS`, `NEWSDOCK_WEB_PAGE_SIZE` win, validates with a small schema, returns `{apiBaseUrl, pollMs, pageSize}`.
- `src/app/layout.tsx`: `await connection()`; `<ConfigProvider value={config}>`. `features/feed/api.ts` takes `apiBase` as a parameter (no module-level constant); `Feed.tsx` reads `pollMs` from the provider.
- Dockerfile: copy `infra/config` is not needed (mounted at runtime); no `ARG`. The compose `web` service mounts the file and sets `NEWSDOCK_CONFIG_FILE`.
- Tests: vitest for `runtime.ts` (env beats file, defaults, bad file) and Feed with a provider; a manual check for AC-14 (change env, `docker compose up -d web`, no build).

## 5. Checks (C-16)

`infra/scripts/check_config.py` (run by `make check-python`; unit-tested in `infra/scripts/tests/`, plus a `rules/` test per CLAUDE.md "test-rules proves each rule fails"):
1. YAML parses; every `common` key is a field of at least one service `Settings`; every service-section key is a field of that service.
2. No key matches the secret pattern.
3. Literal check (AC-11): AST scan of `apps/*/src` and `packages/*/src` (excluding `config.py`, tests, `newsdock_config`) for string literals `gkg.raw|gkg.clean|gkg.dlq` and for the names `MAX_ATTEMPTS`, `RETENTION_DAYS`, `FIRST_RUN_WINDOW`, `MAX_PAYLOAD_BYTES`, `DEFAULT_WINDOW`, `POLL_MS`; docstrings are exempt.

## 6. Failure table

| Failure | Detection | Result |
|---|---|---|
| YAML syntax error | loader | exit 1, path + line |
| Wrong type (`batch_size: "many"`) | pydantic | exit 1, `section.key` + expected type |
| Unknown service key / secret key / missing explicit file | loader | exit 1 naming it |
| Heartbeat file missing | health CLI | unhealthy (same as today) |
| Heartbeat content not an int | health CLI | unhealthy |
| Web file unreadable | `runtime.ts` | logs once, falls back to env then defaults; the page still renders |
| Topic job cannot reach Kafka | AdminClient timeout | non-zero exit (same as today's script) |

## 7. Security

- File is committed, so it is secret-free by rule and by check (AC-7, C-16). Effective-config log redacts. Agent mounts the file read-only; it holds only topology names and tunables (no credentials, no DSN).
- No new network path; no new port.

## 8. Migration order (for /spec-plan)

Loader + tests → one app end to end (sink or ingester) → remaining apps → `newsdock_db` pool → topic job + compose → health CLI + compose healthchecks → web runtime → C-16 checks → docs (CLAUDE.md fixed names, specs/ADRs that repeat topic names, README, `.env.example`). M2a must be committed first (spec risk 1).

## 9. Doc updates caused by D-8

CLAUDE.md "Fixed names" and "Architecture" lines name the topics; ADR-0001/0002, `docs/specs/mvp/design*.md`, `docs/specs/foundation/design-detail.md` and `docs/roadmap.md` repeat them. Plan lists each file; the topics remain the documented **defaults**.
