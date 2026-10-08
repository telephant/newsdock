# ADR-0013: Layered configuration — shared `newsdock_config` package and one YAML file

Status: **Accepted 2026-10-06** (user accepted the recommended defaults at /spec-design externalize-config)

## Context
Each app has its own env-only `config.py`; there is no file source and many tunables are literals (spec §3). The user wants one file with a `common` parent and per-service children, overridable by Docker env, secrets in env only (spec D-1…D-4). The loader must be shared, because six copies of merge logic would drift, but `newsdock_core` must stay I/O-free and apps may not import each other (DR-7).

## Options
1. **Shared package `packages/config` (`newsdock_config`) with a `LayeredSettings` base class** and a custom pydantic-settings file source (inheritance and flattening done in the loader).
2. Put the loader in `newsdock_core` (breaks the "no I/O library" contract: it would read files and env).
3. Use pydantic-settings' stock `YamlConfigSettingsSource` and YAML anchors (`<<: *common`) for inheritance. Simple, but the stock source does not skip fields that env already supplies for aliased fields (spike: both keys reach pydantic and it rejects the pair), cannot report `section.key`, and anchors make env override and per-service filtering impossible.
4. One YAML file per service. Rejected in spec D-1.

File location: `infra/config/newsdock.yaml` (not a new repo-root folder, so no DR-1 exception; compose mounts `./config`).

## Decision
Option 1. Keys nest in YAML and flatten with `_` to field names, so existing env names (`NEWSDOCK_BATCH_SIZE`, aliases) keep working unchanged. Order: init → env → file → defaults. Service sections are strict; `common` keys a service does not declare are skipped, and a repository check ensures every `common` key belongs to some service. Secret-looking keys in the file are an error. The agent receives the whole file read-only but its model declares no Kafka or database fields.

## Consequences
+ One implementation, one error format, backwards-compatible env names, testable with plain pytest. + No new third-party dependency (PyYAML and pydantic-settings already installed). − A new package to maintain and one more import-linter contract. − The agent container can read topology names (no credentials); a per-service slice is the stricter alternative if that ever matters. − The "unknown `common` key" check lives in CI, not at runtime.
