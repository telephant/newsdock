# ADR-0029: The what-happen agent is an independent server in `agents/`

Status: Accepted 2026-10-30 (the user's decision; supersedes [ADR-0028](0028-digest-loop-as-second-entry-point-of-the-agent-app.md))

## Context

ADR-0028 put the what-happen digest into `apps/agent` as a second entry point. Using it showed the cost:

- two different agents (the M1 financial-scoring demo and the digest) shared one app, one image and one `Settings` class, under one environment prefix `NEWSDOCK_AGENT_`. The owner set `NEWSDOCK_AGENT_API_KEY` and the digest, which reads another variable, ignored it;
- both could be pointed at one key and then steal each other's articles (the server keeps one cursor per key);
- there was no "agent server" the owner could start, stop, read about or ship on its own.

`apps/` in this repository means the platform's own services (ingester, processor, sink, api, embedder, web): one workspace, one lockfile, one layout rulebook, one CI. An agent that consumes the platform is a client of it and a different kind of thing.

## Options

1. **Keep it in `apps/agent`.** Rejected: the problems above.
2. **A new app `apps/whathappen`.** Rejected by the owner: an app is a platform service; this is an agent server that should be able to exist without the platform's code.
3. **A top-level `agents/<name>/` folder in this repository, self-contained.** Chosen.
4. **A separate git repository.** The truest independence, but two repositories to keep in step. Option 3 can be turned into option 4 by copying the folder, so this stays open.

## Decision

Option 3. Every independent agent server lives in `agents/<name>/` as its own project:

- its own `pyproject.toml` and lockfile (outside the uv workspace, which lists only `apps/*` and `packages/*`), `Dockerfile`, `compose.yaml`, `Makefile`, `README.md`, `.env` (git-ignored) and `.env.example`;
- **no platform code**: it imports nothing from `apps/*` or `packages/*` and depends on no workspace package. A test in the agent's own suite fails if that ever changes;
- it reaches the platform only over HTTP (MCP at the published API port, with its own key) and the host's Ollama, and joins no platform docker network;
- its settings use their own environment prefix (`WHATHAPPEN_`) and its own key (`WHATHAPPEN_API_KEY`), created by a person in the website at `/admin/agents`;
- its own lint, type and test configuration. The root tooling names its paths explicitly and does not cover it; it is checked with `make -C agents/whathappen check`.

The platform's layout check allows the folder `agents` and, inside each agent, only requires Python to be under `src/<name>/` or `tests/`. The platform's app rules (DR-2, DR-3, DR-6, DR-7 and the import contracts) do not apply to agents.

`apps/agent` returns to what milestone M1 delivered: the demo financial-scoring agent only.

## Consequences

- The owner starts, configures and reads one folder. Keys cannot be mixed up: the variable names differ and the agent has its own entry in the website.
- A second independent agent can be added as `agents/<other>/` without touching the platform.
- Some code is deliberately duplicated: the small MCP client and the heartbeat helper are copies of the platform's. That is the price of independence.
- Root `make check` does not run the agent's tests. Until a CI job for `agents/` is added, run `make -C agents/whathappen check`. A path-filtered CI job is a follow-up.
- Findings that only an outside client sees get recorded: the platform's MCP refuses any `Host` header outside `localhost`, `127.0.0.1` and `api` (HTTP 421), so the agent's container reaches the host under the name `api`; another name needs the platform's `NEWSDOCK_API_MCP_ALLOWED_HOSTS`.
