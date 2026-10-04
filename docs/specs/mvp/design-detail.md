# mvp — Design detail

**Reference only. Not required reading for design approval.** Overview: [design.md](design.md).

## 1. Postgres schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE articles (
  url_hash       text PRIMARY KEY,            -- sha256 hex of normalized URL = public article_id
  seq            bigserial UNIQUE NOT NULL,   -- insert order, cursor basis
  gkg_record_id  text NOT NULL,
  slot           text NOT NULL,               -- YYYYMMDDHHMMSS
  url            text NOT NULL,
  title          text NOT NULL,
  domain         text,
  published_at   timestamptz NOT NULL,
  ingested_at    timestamptz NOT NULL DEFAULT now(),
  themes         text[] NOT NULL DEFAULT '{}',
  persons        text[] NOT NULL DEFAULT '{}',
  orgs           text[] NOT NULL DEFAULT '{}',
  tone           real, tone_pos real, tone_neg real, tone_polarity real,
  word_count     int
);
CREATE INDEX ON articles (published_at DESC);
CREATE INDEX ON articles (ingested_at);
CREATE INDEX ON articles USING gin (themes);
CREATE INDEX ON articles (domain);

CREATE TABLE analyses (
  article_id text REFERENCES articles(url_hash) ON DELETE CASCADE,
  agent_name text NOT NULL,
  payload    jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (article_id, agent_name)         -- resubmission replaces (latest wins)
);

CREATE TABLE ingest_slot (
  slot text PRIMARY KEY, status text NOT NULL,  -- pending | published
  attempts int NOT NULL DEFAULT 0, row_count int, updated_at timestamptz NOT NULL DEFAULT now()
);
```

Roles: `ingester_rw` (ingest_slot), `sink_rw` (articles, analyses delete via cascade), `api_rw` (read articles; write analyses). The agent has no role.

## 2. Algorithms

**Ingester cycle.** `GET lastupdate.txt` (follow redirects) → take line ending `.gkg.csv.zip` → slot from file name → process this slot and every `pending` slot with attempts < 4. Per slot: GET (404, empty, or md5 mismatch → attempts+1, stay pending, log) → unzip → for each line produce `gkg.raw` keyed `<slot>:<row_no>` → `flush()` → mark `published`. Interval default 900 s, minimum enforced 900 s.

**Processor.** Kafka consumer group `processor` on `gkg.raw`, `enable.auto.commit=false`. Per message: split on `\t`; columns ≠ 27 → dlq `bad_column_count`; URL = col 5, title from `<PAGE_TITLE>` in col 27; empty → dlq; normalize URL (lower-case scheme/host, strip fragment and trailing `/`, keep query) → `url_hash`; themes = col 9 (V2, strip `,offset`) falling back to col 8, **empty is normal (86/527 rows)**; persons = col 13, orgs = col 15 (V2 names, strip offsets); tone = col 16 (7 numbers); published_at = col 2. Produce to `gkg.clean` (key `url_hash`) or `gkg.dlq`; flush, then commit offsets per batch. Stateless.

**Sink.** Kafka consumer group `sink`, `enable.auto.commit=false`; batch up to 200 messages / 1 s → `INSERT … ON CONFLICT (url_hash) DO NOTHING` → commit. Retention thread: hourly `DELETE FROM articles WHERE ingested_at < now() - interval '7 days'`.

**Cursor.** `next_cursor = b64("seq:<max seq returned>")`; no cursor → start from now − 24 h worth (`seq` of the oldest article ≥ now−24 h) so a first run does not score the whole store (open to change).

**Search.** Parameterized SQL; `text` = `title ILIKE '%…%'` (escape `%`, `_`); `theme` = `themes @> ARRAY[$1]`; limit clamped.

## 3. REST routes

| Route | Notes |
|---|---|
| `GET /api/articles` | filters as in design.md; `before=<published_at,url_hash>` keyset pagination; each item includes latest `score` per agent if `payload.score` is numeric |
| `GET /api/articles/{article_id}` | article + all analyses |
| `GET /api/health` | DB ping, last ingested slot, Kafka reachable |

## 4. Compose layout

Services: `kafka`, `postgres`, `processor`, `sink`, `ingester`, `api`, `agent`, `web`. Networks: `data` (kafka, postgres, processor, sink, ingester, api) and `agent` (api, agent, web). `agent` has `MCP_URL` and `OLLAMA_URL` only. Healthchecks on kafka, postgres, api. Memory budget target ≤ 8 GB; measure; without a JVM it should be well under 8 GB **[assumption]**.

## 5. Full failure table

| Failure | Detection | Handling |
|---|---|---|
| lastupdate.txt unreachable | HTTP error | log, next cycle |
| md5 mismatch | compare to index line | treat as 404 |
| Kafka unavailable at publish | producer error | slot stays pending; retry next cycle |
| Row publish partially done | slot not `published` | whole slot re-published; downstream dedup absorbs |
| Processor crash | container restart | resume from committed offset; downstream idempotent |
| Poison message | exception in map | catch per row → dlq `bad_field` |
| Sink DB error | exception | no commit, backoff retry |
| Retention delete races with sink | none | independent rows, no issue |
| `submit_analysis` unknown article | FK violation | return MCP error `not_found` |
| Oversized payload | size check > 64 KB | reject |

## 6. Security (MVP)

No auth (local only, M2 backlog). Ports bound to `127.0.0.1`. Secrets in `.env`, git-ignored. SQL parameterized. `submit_analysis` payload is stored and rendered as text in the UI (escaped, never as HTML). Agent has no DB route (AC-13). Respect GDELT: 15-min polling only; attribution in README.

## 7. Eval command (AC-14)

`python -m agent.eval --labels labels.csv` → `labels.csv` is a self-contained snapshot (`url, title, themes, label`) because the 7-day store would expire the articles. Each row is scored with the same prompt and structured-output schema as production (no MCP/DB needed), threshold 0.5; prints precision, recall, F1 and confusion counts. Labelling helper: export a sample from the store (REST) to CSV, then label by hand.

## 8. Repository layout

Monorepo, one git repo. `apps/{ingester,processor,sink,api,agent}` (Python), `apps/web` (Next.js + TS), `packages/core` (shared Python), `infra/` (compose, migrations, topic setup). Component mapping: C-1 `apps/ingester`, C-3 `apps/processor`, C-4 `apps/sink`, C-6 `apps/api`, C-7 `apps/agent`, C-8 `apps/web`. Rules: apps import `packages/*` only, never each other; UI types are generated from the API's OpenAPI schema. Tooling (uv workspace, pnpm, CI path filters) is chosen in the plan. **[assumption]**
