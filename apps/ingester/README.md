# newsdock-ingester

Python app, component C-1. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

Polls the GDELT GKG index every 15 minutes (never faster), downloads each new slot, checks its md5 and publishes one raw message per row to Kafka topic `gkg.raw`. Tracks slot state (`pending`, `published`, `failed`) in Postgres.

## Entrypoint

`python -m newsdock_ingester` runs `src/newsdock_ingester/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `httpx` and `confluent-kafka` (client libraries), `newsdock-db`.

## Run/Test

```bash
make test APP=ingester                      # unit tests
uv run python -m newsdock_ingester          # run the entrypoint
make build APP=ingester                     # build the image newsdock-ingester:dev
```
