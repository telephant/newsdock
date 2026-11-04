# newsdock-extractor

Python app, component C-80 (spec `body-extraction`, [ADR-0034](../../docs/adr/0034-extractor-app-on-the-data-network.md), [ADR-0035](../../docs/adr/0035-polite-and-ssrf-safe-fetching.md), [ADR-0036](../../docs/adr/0036-bodies-and-passages-tables-halfvec-and-a-discovery-queue.md)).

## Purpose

Fetches the web page behind every canonical article, extracts the main text and stores it in `article_bodies` (with a status) and `article_passages` (pieces of about 1,000 characters that the embedder turns into vectors), so agents can read the text and search it. It is the only component that talks to the open web: it obeys robots.txt (Protego, including Crawl-delay), identifies itself honestly, takes one page per site at a time, refuses private addresses, caps size and time, and never keeps cookies. It reads `articles` only and never touches Kafka, the sink or the API, so ingestion never waits on it.

Status: the worker runs end to end (discovery, queue, fetching, extraction, passages, retries, heartbeat). It runs as the compose service `extractor` (profile `apps`, network `data`, no Kafka), and the passages it writes get their vectors from the embedder's second pass.

## Entrypoint

`python -m newsdock_extractor` runs `src/newsdock_extractor/__main__.py`, which loads `Settings` from `config.py` and runs the loop. Settings live in `infra/config/newsdock.yaml` (`extractor:`).

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic (extraction, passage splitting, scheduling, retry rules), `adapters/` holds all I/O (HTTP fetcher, robots, address guard, SQLAlchemy, healthcheck), `config.py` is the only place environment variables are read.

## Dependencies

`newsdock-config`, `newsdock-db` (role `extractor_rw`), `httpx`, `trafilatura` (text extraction), `protego` (robots.txt) and `pydantic-settings`.

## Run/Test

```bash
make test APP=extractor                 # unit tests
make test-infra SCENE=extractor         # Docker tests (real Postgres, local test web server)
uv run python -m newsdock_extractor     # run the entrypoint
make build APP=extractor                # build the image newsdock-extractor:dev
```
