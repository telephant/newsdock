# whathappen

An independent agent server for newsdock. It plays the part of an outside user: it reads the news through the platform's **MCP** endpoint with its own key, merges headlines about the same event, ranks the stories by how many outlets carry them and how negative they are, asks a local **Ollama** model for one sentence per listed story, and writes an hourly markdown digest in which every story is a link. Running it shows that the whole flow works: website account, agent key, MCP, cursor, local model.

It is **not part of the platform**. It imports no newsdock code, has its own `pyproject.toml`, lockfile, Dockerfile, compose file and `.env`, and talks to the platform only over HTTP. It could be moved into its own repository by copying this folder.

The sentences are grounded in the article where possible: for each listed story the agent asks `get_article` for the stored page text (the platform's extractor fetches it, M3d) and gives the model the first `WHATHAPPEN_SUMMARY_BODY_CHARS` of it next to the headlines. A story whose text is not stored (yet) falls back to headlines only, where the sentence can be wrong — open the links.

## Quick start

You need the platform running (API on port 8000, website on 3000), Ollama running with the model pulled (`ollama pull qwen3:4b-instruct`), `uv`, and an account on the website.

1. **Get a key.** Log in at `http://127.0.0.1:3000` (use that exact host, not `localhost`), open `/admin/agents`, create an agent named `whathappen` and click **Copy key**. It is shown only once.
2. **Configure.**
   ```
   cd agents/whathappen
   cp .env.example .env        # then set WHATHAPPEN_API_KEY=ndk_...
   ```
   The key must be this agent's own: two programs sharing one key would take each other's articles.
3. **Run one cycle.** `make once` prints the digest and writes `output/latest.md`. Open that file: every story is a link.
4. **Run it as a server.** `make up` starts it in Docker (hourly digests, restarts on failure); `make logs` follows it; `make down` stops it. `make run` is the same loop without Docker.

## What one cycle does

1. Pages through `list_new_articles` from the agent's stored position (explicit cursors, 200 per page, asking for `tone_neg`) until a short page or `WHATHAPPEN_MAX_ARTICLES`.
2. **Groups** headlines about the same event with a lexical title match (shared significant words, within 48 hours, never two pages of one domain). Trailing outlet names (`| WKZO`) are dropped first.
3. **Scores** each group as `sources × (1 + tone_neg / 10)`: `sources` is how many outlets carry the story, `tone_neg` how negative GDELT scores it. If the platform does not return tone yet, the score is the source total and the file says "Ranked by outlets covering a story."
4. **Selects** groups carried by at least 2 outlets: the best 5 become **Top stories**, the rest go under plain labels (Conflict & Security, Politics & Government, Business & Markets, Crime & Courts, Health, Disasters & Accidents, Other) chosen by a vote over their GDELT theme codes.
5. Asks Ollama for one sentence per listed story. It first asks `get_article` for the story's stored page text (the shown headline's article, then up to `WHATHAPPEN_BODY_LOOKUPS_PER_GROUP` distinct headlines) and puts the first `WHATHAPPEN_SUMMARY_BODY_CHARS` characters of it in the prompt next to the headlines; without stored text the prompt is headlines only, and a story with a single headline then gets no sentence (it would only repeat it). A failed `get_article` costs the excerpt, never the digest.
6. Writes `output/YYYY-MM-DD/HHMM.md` (UTC) and `output/latest.md`, **then** acknowledges the cursor. A crash in between re-reads the window (a second file) and never loses articles.

An empty hour writes nothing and acknowledges nothing. An hour with articles but no story carried by 2 or more outlets writes a short note and acknowledges. If Ollama is down, stories show their links without a sentence. The first line of every digest is the invisible marker `<!-- whathappen:story-first -->`.

**Limits to know.** The hourly view sees a story's outlet count early, and the count includes every copy: radio-station networks and local-newspaper chains republish one headline on dozens of sites, so a soft story can rank high. Sections follow GDELT theme codes, which are noisy, so some stories sit under the wrong label. Both are measured in `docs/specs/digest-top-stories/spike.md`. On a live read the owner also judged the **summaries and categories poor**; this is a demo and that is a known limitation (see `docs/specs/digest-top-stories/verify.md`, F-8).

## Removing the old theme digest's output

The first version of this agent grouped by theme and wrote a `baseline.json` next to its digests. After upgrading, remove those once:

```
make clean-old        # lists the old files, deletes nothing
make clean-old-yes    # deletes exactly those files
```

A file is old if it is `baseline.json`, or a `latest.md` / `YYYY-MM-DD/HHMM.md` whose first line is not `<!-- whathappen:story-first -->`. Anything else in `output/` (your own notes, other folders, symlinks, unreadable files) is listed as kept and never touched, and the hourly loop never runs this.

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
| `WHATHAPPEN_TOP_STORIES` | `5` | stories in the Top stories block |
| `WHATHAPPEN_MAX_SECTIONS` / `GROUPS_PER_SECTION` | `6` / `4` | sections, and stories per section |
| `WHATHAPPEN_MIN_GROUP_SOURCES` | `2` | a story carried by fewer outlets is not listed |
| `WHATHAPPEN_ALSO_PER_GROUP` | `3` | other headlines shown (and sent to the model) per story |
| `WHATHAPPEN_GROUP_WINDOW_HOURS` | `48` | a headline joins a story within this of its first |
| `WHATHAPPEN_TONE_DIVISOR` | `10` | score = sources × (1 + tone_neg / divisor) |
| `WHATHAPPEN_SUMMARY_BODY_CHARS` | `1200` | stored article text given to the model per story; `0` = headlines only |
| `WHATHAPPEN_BODY_LOOKUPS_PER_GROUP` | `3` | distinct headlines asked (`get_article`) for a stored body, per story |
| `WHATHAPPEN_SECTION_MIN_HITS` | `1` | theme hits a label needs to claim a story |
| `WHATHAPPEN_SECTION_LABELS` | built-in map | JSON `{"Label": ["THEME_PREFIX", …]}`, in priority order |

The full list with every default is in `src/whathappen/config.py`. In Docker, `WHATHAPPEN_DOCKER_MCP_URL` and `WHATHAPPEN_DOCKER_OLLAMA_URL` in `.env` override where the container finds the platform and Ollama.

## When something goes wrong

- **"the platform rejected this agent's key (HTTP 401)"**: the key is wrong or revoked, or has a stray space or quote in `.env`. Create a new one in the website.
- **`421 Invalid Host header` / "unhandled errors in a TaskGroup"** from a container: the platform's MCP accepts only the Host names `localhost`, `127.0.0.1` and `api`. The compose file maps `api` to your host for that reason. For another host name, add it to the platform's `NEWSDOCK_API_MCP_ALLOWED_HOSTS`.
- **"empty window"**: nothing new since the last cycle; normal. The platform ingests every 15 minutes.
- **A story has no sentence under its headline**: it has a single headline and no stored page text yet (the extractor fetches politely, so fresh articles lag), or Ollama is not reachable or the model is not pulled.
- **Sentences read like reworded headlines**: the platform has no stored text for those articles — check the `extractor` service is running and `get_article` returns `body_status: ok`; headlines-only is the fallback.
- **"Ranked by outlets covering a story." without "and negative tone"**: the platform did not return `tone_neg`; rebuild its API from the `tone-in-summary` code.
- **`missing .env`**: run `cp .env.example .env` and set the key.

## Develop

```
make setup     # uv sync into .venv
make check     # ruff, mypy strict, tests
```

Layout: `src/whathappen/domain/` is pure logic (no I/O), `adapters/` holds the MCP client, Ollama client, files and heartbeat, `config.py` is the only place the environment is read. `tests/unit/test_packaging.py` fails if any source file ever imports newsdock code or the compose file joins a platform network.

Spec and design history: `docs/specs/digest-top-stories/` (the story-first digest, ADR-0031) and `docs/specs/what-happen/` (the first, theme-based digest; superseded for the digest shape), decision records ADR-0028 (superseded), ADR-0029 and ADR-0031.
