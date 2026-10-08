# newsdock-config

Shared configuration loader (`newsdock_config`, ADR-0013). Each service's `Settings` extends `LayeredSettings`, which resolves every field from, in order: init arguments, environment variables, the YAML file named by `NEWSDOCK_CONFIG_FILE` (`common:` merged under the service section), then the code default.

- Nested YAML keys flatten with `_` to field names (`kafka.topics.clean` → `kafka_topics_clean`, env `NEWSDOCK_KAFKA_TOPICS_CLEAN`).
- A key unknown to the service section, a secret-looking key (`password`, `secret`, `token`, `database_url`, `*_dsn`) or an unreadable explicit file fails startup with a `ConfigError` naming it.
- `common` keys the service does not declare are skipped; `infra/scripts/check_config.py` verifies each belongs to some service.
- No app, `newsdock_core` or `newsdock_db` import; `domain/` code never imports this package.

Test: `uv run pytest packages/config`.
