# newsdock-processor

Python app, component C-3. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

Stateless Kafka consumer: reads `gkg.raw`, parses the 27 GKG columns, validates and routes each row to `gkg.clean` or the dead-letter topic `gkg.dlq`.

## Entrypoint

`python -m newsdock_processor` runs `src/newsdock_processor/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `confluent-kafka`.

## Run/Test

```bash
make test APP=processor                      # unit tests
uv run python -m newsdock_processor          # run the entrypoint
make build APP=processor                     # build the image newsdock-processor:dev
```
