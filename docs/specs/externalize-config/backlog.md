# externalize-config — Backlog (after this milestone)

- **Hot reload (P3):** re-read the config file without restarting a service. Why: only needed if a tunable must change on a live system; restart is fine locally.
- **Config schema published as JSON Schema (P3):** generate it from the pydantic models for editor autocomplete in `newsdock.yaml`.
- **Per-environment overlays (P2, M5):** `newsdock.dev.yaml` / `newsdock.prod.yaml` layering, and secrets from a secret manager. Why: cloud deploy needs it; local does not.
- **Compose-managed broker and image settings (P3):** Kafka listeners, partitions, image tags in config. Out of this milestone by D-5.
- **Agent prompt and story-key tuning as config (P3):** kept in code by D-7; revisit if tuning becomes frequent.
- **Config in the UI / admin endpoint (P3):** show the effective, redacted config of each service. Why: debugging.

## Follow-ups from /spec-verify (2026-10-07)

- **CI path filter for config (P1):** add `infra/config/**` and `infra/compose.yaml` to the Python/infra filters in `.github/workflows/ci.yml`, push, and read the run (`gh run watch`). Why: a config-only change currently skips the job that validates it.
- **Automated test for `uvicorn_workers > 1` (P3):** only checked by hand (two processes, health 200).
- **Agent gets a per-service config slice (P3):** replace the whole-file mount if topology names ever become sensitive (ADR-0013 consequence).
