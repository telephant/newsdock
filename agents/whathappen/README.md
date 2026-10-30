# whathappen

An independent agent server for newsdock. It plays the part of an outside user: it reads the news through the platform's **MCP** endpoint with its own key, asks a local **Ollama** model for one sentence per rising theme, and writes an hourly markdown digest in which every story is a link. Running it shows that the whole flow works: website account, agent key, MCP, cursor, local model.

It is **not part of the platform**. It imports no newsdock code, has its own `pyproject.toml`, lockfile, Dockerfile, compose file and `.env`, and talks to the platform only over HTTP. It could be moved into its own repository by copying this folder.

Headlines only: the data has no article text, so the sentences describe headlines and can be wrong. Open the links.

## Quick start

You need the platform running (API on port 8000, website on 3000), Ollama running with the model pulled (`ollama pull qwen3:4b-instruct`), `uv`, and an account on the website.

1. **Get a key.** Log in at `http://127.0.0.1:3000` (use that exact host, not `localhost`), open `/admin/agents`, create an agent named `whathappen` and click **Copy key**. It is shown only once.
2. **Configure.**
   ```
   cd agents/whathappen
   cp .env.example .env        # then set WHATHAPPEN_API_KEY=ndk_...
   ```
   The key must be this agent's own: two programs sharing one key would take each other's articles.
3. **Run one cycle.** `make once` prints the digest and writes `output/latest.md`. Open that file: each bullet is a link.
4. **Run it as a server.** `make up` starts it in Docker (hourly digests, restarts on failure); `make logs` follows it; `make down` stops it. `make run` is the same loop without Docker.

## What one cycle does

1. Pages through `list_new_articles` from the agent's stored position (explicit cursors, 200 per page) until a short page or `WHATHAPPEN_MAX_ARTICLES`.
2. Counts themes in plain Python and ranks them against a rolling 24-hour baseline (`×N vs usual`); the first 3 cycles rank by volume ("no baseline yet"). Generic GDELT codes are skipped.
3. Picks the best stories per theme (most sources, then newest), each story under one theme only.
4. Asks Ollama for one sentence per theme, from that theme's three shown headlines only.
5. Writes `output/YYYY-MM-DD/HHMM.md` (UTC) and `output/latest.md`, **then** acknowledges the cursor, then saves the baseline. A crash in between re-reads the window (a second file) and never loses articles.

An empty hour writes nothing and acknowledges nothing. If Ollama is down, sections show "Summary unavailable." with their links.

## Settings

All environment variables with the prefix `WHATHAPPEN_`, also read from `agents/whathappen/.env`. The environment wins over the file.

| Variable | Default | Meaning |
|---|---|---|
| `WHATHAPPEN_API_KEY` | none | this agent's key (secret; shown once in the website) |
| `WHATHAPPEN_MCP_URL` | `http://127.0.0.1:8000/mcp` | the platform's MCP endpoint |
| `WHATHAPPEN_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama on the host |
| `WHATHAPPEN_MODEL` | `qwen3:4b-instruct` | the model that writes the sentences |
| `WHATHAPPEN_INTERVAL_SECONDS` | `3600` | time between cycles |
| `WHATHAPPEN_OUTPUT_DIR` | `output` | digests (relative paths are inside this folder) |
| `WHATHAPPEN_MAX_THEMES` / `STORIES_PER_THEME` | `8` / `3` | sections and links per section |
| `WHATHAPPEN_SKIP_THEME_PREFIXES` | `TAX_,WB_,EPU_,…` | generic theme codes to drop |

The full list with every default is in `src/whathappen/config.py`. In Docker, `WHATHAPPEN_DOCKER_MCP_URL` and `WHATHAPPEN_DOCKER_OLLAMA_URL` in `.env` override where the container finds the platform and Ollama.

## When something goes wrong

- **"the platform rejected this agent's key (HTTP 401)"**: the key is wrong or revoked, or has a stray space or quote in `.env`. Create a new one in the website.
- **`421 Invalid Host header` / "unhandled errors in a TaskGroup"** from a container: the platform's MCP accepts only the Host names `localhost`, `127.0.0.1` and `api`. The compose file maps `api` to your host for that reason. For another host name, add it to the platform's `NEWSDOCK_API_MCP_ALLOWED_HOSTS`.
- **"empty window"**: nothing new since the last cycle; normal. The platform ingests every 15 minutes.
- **"Summary unavailable."**: Ollama is not reachable, or the model is not pulled.
- **`missing .env`**: run `cp .env.example .env` and set the key.

## Develop

```
make setup     # uv sync into .venv
make check     # ruff, mypy strict, tests
```

Layout: `src/whathappen/domain/` is pure logic (no I/O), `adapters/` holds the MCP client, Ollama client, files and heartbeat, `config.py` is the only place the environment is read. `tests/unit/test_packaging.py` fails if any source file ever imports newsdock code or the compose file joins a platform network.

Spec and design history: `docs/specs/what-happen/` in the repository, decision records ADR-0028 (superseded) and ADR-0029.
