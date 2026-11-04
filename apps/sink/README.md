# newsdock-sink

Python app, component C-4. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

Kafka consumer that upserts `gkg.clean` messages into Postgres (`ON CONFLICT DO NOTHING`). Since M3c `events-mentions` (ADR-0032/0033) it also reads `events.clean` and `mentions.clean` in the same loop and upserts them into `events` (newer `date_added` wins) and `mentions` (newer `mention_time` wins, key `(event_id, url_hash)`); duplicate keys in a batch are collapsed first, a batch Postgres rejects is retried row by row, and offsets are committed once after all three kinds are written. It runs the hourly retention delete (`retention_days`, default 7, in `infra/config/newsdock.yaml`).

## Entrypoint

`python -m newsdock_sink` runs `src/newsdock_sink/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `confluent-kafka` and `newsdock-db`.

## Run/Test

```bash
make test APP=sink                      # unit tests
uv run python -m newsdock_sink          # run the entrypoint
make build APP=sink                     # build the image newsdock-sink:dev
```
