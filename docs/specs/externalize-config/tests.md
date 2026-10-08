# externalize-config — Tests

Derived from the Given/When/Then ACs in [spec.md](spec.md) §6. Write each test before the code (T-NN tasks name the TCs).

## Test data and fixtures

- **Config files:** built per test with pytest `tmp_path` (YAML text inline in the test); pointed at via `monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", ...)`. No shared fixture file except the committed real `infra/config/newsdock.yaml` (TC-4, TC-14).
- **Before-snapshot of today's defaults:** `infra/scripts/tests/fixtures/config_defaults_before.json`, generated from the **current** code in T-02 before any settings change (existing fields only: field name → default per app). New fields are checked against the inventory in `design-detail.md` §2. This is what makes AC-4 a real regression check.
- **Fakes:** the existing fake source/publisher/repo in `apps/ingester/tests/unit/test_cycle.py`; fake Kafka producers/consumers already used by processor and sink tests; httpx `MockTransport` for agent/ollama; a fake clock for retention.
- **Integration (Docker):** Kafka from `make test-infra SCENE=kafka`; stack from `SCENE=stack`. Topic names use `test.*` to avoid touching the real ones.
- **Web:** vitest with temp YAML files and `process.env` stubs.
- **Real GDELT data:** not needed; this feature does not change parsing.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given a file `ingester: {poll_interval_seconds: 1800}`, no env; When `ingester.Settings()`; Then `poll_interval_seconds == 1800` (`packages/config/tests/unit/test_settings.py`, `apps/ingester/tests/unit/test_config.py`) |
| TC-2 | AC-2 | unit | Given `common.log_level: DEBUG`, `ingester.log_level: WARNING`, nothing under `sink`; When both settings load; Then sink DEBUG, ingester WARNING. Edge: nested `common.kafka.topics.clean` reaches sink as `kafka_topics_clean` |
| TC-3 | AC-3 | unit | Given file 1800 and env `NEWSDOCK_POLL_INTERVAL_SECONDS=2400`; Then 2400. Edge: aliased field — file `kafka.bootstrap_servers: kafka:9092` plus env `KAFKA_BOOTSTRAP_SERVERS=envk:1` loads `envk:1` with no "extra input" error; env `NEWSDOCK_KAFKA_BOOTSTRAP_SERVERS` also wins |
| TC-4 | AC-4 | unit | Given no file and no env; When each app's settings load; Then every existing field equals `config_defaults_before.json` and every new field equals the inventory default in `design-detail.md` §2 (one test per app, in each app's `test_config.py`; the check tool re-runs the same comparison for the committed file: committed `infra/config/newsdock.yaml` values equal the defaults) |
| TC-5 | AC-5 | unit | Given `NEWSDOCK_CONFIG_FILE=/no/such.yaml`; When settings load; Then `ConfigError` naming the path, and `python -m newsdock_ingester` exits non-zero. Edge: unparsable YAML names path and line; variable unset is not an error |
| TC-6 | AC-6 | unit | Given `sink: {batchsize: 3}`; When `sink.Settings()`; Then error text contains `sink.batchsize`. Edge: unknown key in `common` that no model declares is skipped at runtime (the check in TC-14 catches it) |
| TC-7 | AC-7 | unit | Given a file with `database_url` (or `password`, `*_token`, `*_dsn`) in `common` or any section; Then loading fails naming the key; And with the file clean and env `DATABASE_URL` set, `newsdock_db.Settings().database_url` loads from env |
| TC-8 | AC-8 | unit | Given `kafka_topics_clean=gkg.clean.test`, `kafka_topics_dlq=gkg.dlq.test`; When the processor routes a valid row and a bad row; Then outputs go to those topics (`apps/processor/tests/unit/test_route.py`) |
| TC-9 | AC-8 | unit | Given sink and ingester settings with custom topics; When their Kafka adapters are built with fake client factories; Then the sink subscribes to the custom clean topic and dead-letters to the custom dlq, and the ingester produces to the custom raw topic |
| TC-10 | AC-8 | integration | Given Kafka and settings with `test.raw/test.clean/test.dlq`, 1 partition; When the topic job runs twice; Then the three topics exist with the configured partitions and the second run exits 0 (`apps/processor/tests/integration/test_topics.py`) |
| TC-11 | AC-9 | unit | Given `max_attempts=2` passed from settings; When a slot returns 404 on two consecutive cycles; Then the slot is `failed` after the second and is not retried a third time (`apps/ingester/tests/unit/test_cycle.py` via `Settings` wiring) |
| TC-12 | AC-9 | unit | Given a file with `poll_interval_seconds: 60`; Then effective value is 900 (floor), and 1800 stays 1800. Edge: `http_timeout_seconds` from file reaches the httpx client (fake transport records it) |
| TC-13 | AC-10 | unit | Given `retention_days=3` and a fixed "now"; When the cutoff is computed through the sink wiring; Then cutoff = now − 3 days; default 7 (`apps/sink/tests/unit/test_retention.py`) |
| TC-14 | AC-11 | unit | Given the real tree; When `infra/scripts/check_config.py` runs; Then exit 0, covering: every file key known, no secret key, no listed literal outside config (`infra/scripts/tests/test_check_config.py`) |
| TC-15 | AC-11 | rule | Given a temp module adding `"gkg.clean"` (and separately `MAX_ATTEMPTS = 4`) under an app `src/`; When the check runs; Then it fails naming file and literal; temp file removed (`infra/scripts/tests/rules/test_rules.py`) |
| TC-16 | AC-11 | unit | Given settings with custom values; Then the API honours `search_page_max`, `list_new_page_max`, `max_payload_bytes` (error message shows the configured cap) and `first_run_window_minutes` (`apps/api/tests/unit/test_service.py`) |
| TC-17 | AC-11 | unit | Given settings with custom values; Then the agent loop uses `batch_limit`, the Ollama client uses `ollama_timeout_seconds` and `ollama_temperature`, and `make_engine` receives the `database_*` pool settings (`apps/agent/tests/unit`, `packages/db/tests/unit`) |
| TC-18 | AC-12 | unit | Given a file with `common.kafka.*`, a `sink:` section and an `agent:` section; When `agent.Settings()` loads; Then it succeeds and the model has no field starting `kafka_` or `database_` (`apps/agent/tests/unit/test_config.py`; keeps TC-35 of the MVP: unknown `NEWSDOCK_AGENT_*` env still fails) |
| TC-19 | AC-12 | unit | Given `agent: {kafka_bootstrap_servers: x}` (and separately `database_pool_size`); Then loading fails naming the key |
| TC-20 | AC-13 | unit | Given a heartbeat file containing `2400` with mtime 25 min ago; When the health check runs; Then exit 0; at 45 min exit 1; missing file or non-integer content exit 1 (`packages/config/tests/unit/test_health.py`) |
| TC-21 | AC-13 | unit | Given each worker's settings; When `heartbeat_max_age_seconds` is derived; Then ingester 900→1200, 1800→2400; agent loop 60→120; processor and sink 120; and the worker writes that number into the file on each beat |
| TC-22 | AC-13 | integration | Given `make up` with the file mounted; When all services run for 2 minutes; Then ingester, processor, sink, api, agent and web are `healthy` via the new healthchecks (`infra/scripts/tests/test_stack.py`, SCENE=stack) |
| TC-23 | AC-14 | unit (web) | Given `NEWSDOCK_CONFIG_FILE` with `web: {api_base_url: http://f:1, poll_ms: 5000}`; Then `getRuntimeConfig()` returns it; env `NEWSDOCK_WEB_API_BASE_URL` beats the file; neither set returns today's defaults; unreadable file falls back to env then defaults without throwing (`apps/web/src/lib/config/runtime.test.ts`) |
| TC-24 | AC-14 | unit (web) | Given a `ConfigProvider` with `apiBaseUrl: http://x:9`; When Feed renders and fetches; Then the request URL starts with `http://x:9/api/articles` and polling uses `pollMs` (`apps/web/src/features/feed/Feed.test.tsx`) |
| TC-25 | AC-14 | manual | See checklist below (one image, runtime change, no rebuild) |
| TC-26 | AC-7 | unit | Given settings containing a secret-pattern field value; When the effective config is logged; Then the value is `***` and non-secret values are shown (`packages/config/tests/unit/test_settings.py`) |

## Manual checklist (TC-25, AC-14)

1. `make build APP=web`; note the image id (`docker image inspect newsdock-web:dev --format '{{.Id}}'`).
2. `make up`; open `http://127.0.0.1:3000`; DevTools network: the feed requests go to `http://127.0.0.1:8000/api/articles`.
3. Without rebuilding: set `NEWSDOCK_WEB_API_BASE_URL=http://localhost:8000` for the `web` service (compose override or `.env`), `docker compose up -d web`.
4. Reload: requests now go to `http://localhost:8000`; the image id from step 1 is unchanged.
5. Also check that changing `web.poll_ms` in `infra/config/newsdock.yaml` and restarting `web` changes the polling interval.

## AC coverage (checked by grep in plan validation)

| AC | TCs |
|---|---|
| AC-1 | TC-1 |
| AC-2 | TC-2 |
| AC-3 | TC-3 |
| AC-4 | TC-4 |
| AC-5 | TC-5 |
| AC-6 | TC-6 |
| AC-7 | TC-7, TC-26 |
| AC-8 | TC-8, TC-9, TC-10 |
| AC-9 | TC-11, TC-12 |
| AC-10 | TC-13 |
| AC-11 | TC-14, TC-15, TC-16, TC-17 |
| AC-12 | TC-18, TC-19 |
| AC-13 | TC-20, TC-21, TC-22 |
| AC-14 | TC-23, TC-24, TC-25 |

## Measurements (not pass/fail)

The spec has no provisional targets. One non-gating measurement from the design: wall time of one `python -m newsdock_<app>.adapters.healthcheck` run inside its container (design cost note, ADR-0015). Record in `verify.md`; investigate only if it approaches the 5 s healthcheck timeout.
