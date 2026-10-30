# newsdock-agent

Python app, component C-7. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

Demo financial-relevance agent: an MCP client that lists new articles, scores them with a local Ollama model and submits the analysis back. Has no database credentials (AC-13).

## Entrypoint

`python -m newsdock_agent` runs `src/newsdock_agent/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `the `mcp` client SDK and an Ollama client`.

## What-happen digest (M2g)

A second entry point in this app, `python -m newsdock_agent.digest`, writes an hourly "what happened" digest as a markdown file in which every story is a link. It reads only through MCP (no database or Kafka access), ranks themes in plain Python against a rolling 24-hour baseline, and asks a local Ollama model (`digest_model`, default `qwen3:4b-instruct`, `ollama pull qwen3:4b-instruct`) for one sentence per theme. It is a test harness for the server, not a product: it sees headlines only, so read the links, not just the sentences. Spec: `docs/specs/what-happen/`, decision: ADR-0028.

```bash
make agent-create NAME=whathappen         # a separate agent, so the digest has its own cursor
# paste the printed key into .env as NEWSDOCK_DIGEST_API_KEY=...
make digest-once                          # one cycle on the host, prints the digest
docker compose --env-file .env -f infra/compose.yaml --profile apps up -d digest   # hourly service
```

- Output: `infra/digests/YYYY-MM-DD/HHMM.md` (UTC run time) and `infra/digests/latest.md`; the folder is git-ignored. Create it before `up` on Linux (`mkdir -p infra/digests`) so it is not root-owned.
- The first hours rank themes by plain volume and say "no baseline yet"; "rising" starts after 3 stored cycles.
- The cursor moves only after the file is written, so a crash re-reads the window (a second file, no gap). An empty hour writes nothing.
- If Ollama is down, sections show "Summary unavailable." with their links.
- Settings: the `digest_*` rows in the `agent:` section of `infra/config/newsdock.yaml` (interval, model, themes and stories shown, skip-list, article cap). The key is env-only.

## Run/Test

```bash
make test APP=agent                      # unit tests
uv run python -m newsdock_agent          # run the entrypoint
make build APP=agent                     # build the image newsdock-agent:dev
```
