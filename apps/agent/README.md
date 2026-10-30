# newsdock-agent

Python app, component C-7. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

Demo financial-relevance agent: an MCP client that lists new articles, scores them with a local Ollama model and submits the analysis back. Has no database credentials (AC-13).

## Entrypoint

`python -m newsdock_agent` runs `src/newsdock_agent/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `the `mcp` client SDK and an Ollama client`.

## Run/Test

```bash
make test APP=agent                      # unit tests
uv run python -m newsdock_agent          # run the entrypoint
make build APP=agent                     # build the image newsdock-agent:dev
```
