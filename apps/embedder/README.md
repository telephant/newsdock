# newsdock-embedder

Python app, component C-35 (spec `semantic-search`, [ADR-0024](../../docs/adr/0024-embedder-worker-and-embedding-package.md)).

## Purpose

Fills `articles.embedding` so agents can search by meaning. It polls Postgres for canonical articles with no embedding (or one from another model), newest first, embeds their titles in batches through Ollama (`nomic-embed-text`, 768 dimensions) and writes the vector and the model name. It never touches Kafka or the sink: an article insert never waits on it, and Ollama being down leaves rows empty until the next pass (backoff, heartbeat kept). Old rows and rows from a previous model are picked up by the same query.

## Entrypoint

`python -m newsdock_embedder` runs `src/newsdock_embedder/__main__.py`, which loads `Settings` from `config.py`, wires the Postgres and Ollama adapters and runs the loop. Settings live in `infra/config/newsdock.yaml` (`embedder:` plus the shared `embedding_*` keys under `common:`); `OLLAMA_URL` overrides the Ollama address.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic (the worker pass, skip list, backoff), `adapters/` holds all I/O (SQLAlchemy, Ollama, healthcheck), `config.py` is the only place environment variables are read.

## Dependencies

`newsdock-config`, `newsdock-db` (role `embedder_rw` may update only the two embedding columns), `newsdock-embedding` (the shared Ollama client and text recipe) and `pydantic-settings`. Needs Ollama on the host with the model pulled: `ollama pull nomic-embed-text`.

## Run/Test

```bash
make test APP=embedder                  # unit tests
make test-infra SCENE=embedder          # Docker tests (real Postgres, fake Ollama)
uv run python -m newsdock_embedder      # run the entrypoint
make build APP=embedder                 # build the image newsdock-embedder:dev
```
