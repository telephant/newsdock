# Design detail — harder-search-eval

Reference only; not required reading for approval.

## 1. Builder (C-90)

Inputs: `--slots N` (consecutive 15-minute slots ending at a given slot, default chosen until enough clusters, see §5), `--distractors M`, `--out` directory, Ollama URL and chat model.

Steps (pure functions first, I/O last):

1. `parse_slot(gkg_text, mentions_text, slot)` → articles (`newsdock_core.gkg.parse_row`) and mentions (`newsdock_core.mentions.parse_mention_row`); bad rows dropped.
2. `collapse(articles)` → one article per `story_key` (first by id), so syndicated copies are one.
3. `derive_clusters(articles, mentions)` → `{event_id: [article ids]}` for events whose collapsed members number 2 or more. An article appears in every cluster whose event it mentions.
4. `pick_seeds(clusters)` → one seed per cluster, the member with the lowest id (deterministic); optional cap per theme so one story cannot fill the set **[assumption]**.
5. Paraphrase (I/O): for each seed, two prompts to Ollama `/api/chat` (temperature 0, seed fixed): kind `paraphrase` ("write one short search query a reader would type to find news about this event; do not reuse the title's distinctive words") and kind `keywords` ("2 to 4 keywords"). The output is trimmed to one line.
6. `check_fixture(corpus, queries)` → the AC-1/3/4 rules, raising on a violation. Queries failing AC-3 (equal to or containing a title) are dropped, not retried.
7. Write the two JSON files, sorted by id, with a `built` header (slots, model, date) in the queries file.

Corpus = all cluster members + `M` distractors drawn by a seeded `random.Random` from the remaining collapsed articles.

## 2. Fixture shapes

`search_eval_corpus.json`: `[{"id": "<url_hash>", "title": "...", "url": "...", "slot": "..."}]`.
`search_eval_queries.json`: `{"built": {...}, "queries": [{"query": "...", "kind": "paraphrase", "cluster": 1331041647, "seed": "<id>", "expected": ["<id>", ...]}]}`.

## 3. Harness (C-92)

- `load_dataset(name)`: `easy` (the existing `corpus.json`/`queries.json`, no seed, expected as today) or `events` (the new fixture).
- `embed_corpus(dataset, doc_prefix)` → vectors; `load_db(engine, corpus, vectors)`.
- `run_queries(service, repo, plain, queries, rrf_k, candidates, query_prefix)` → per query the four ranked id lists with the seed removed. `rrf_k` and `candidates` are `SemanticService` constructor values, so the sweep builds a service per pair without touching the database.
- Metrics reuse `recall_at_k` and `reciprocal_rank` (existing, tested).
- `noise(found)` → for each query `len((set(vector[:5]) & expected) - set(hybrid[:5]))`, and the same with the full-text list; totals printed.
- `paired_bootstrap(a, b, seed=0, n=1000)` → 95% interval of `mean(a - b)` over queries.
- Sweep grid (starting values **[assumption]**, editable in one constant): prefix {on, off} × `rrf_k` {10, 30, 60, 100} × `candidates` {20, 50, 100}.
- Output: overall table, by-kind table, noise line, sweep table, and for each setting the winner under the rule.

## 4. Decision record

After the real-model run the numbers and the keep/change per setting go in ADR-0039's "Result" section (or `verify.md`). A change to `rrf_k` or `candidates` edits `infra/config/newsdock.yaml` and the `Settings` default together, then `make config-python`. A prefix change is **not** applied: the embedder's re-embed trigger is the model name, so production vectors would be stale; it becomes a follow-up with a re-embed plan.

## 5. Sizing (provisional)

One real slot gave 83 events with 2 or more different titles (spec §3). The builder starts with 8 slots and reports the cluster count; it stops with an error below a floor set when first run (not a requirement). Fixture size is reported; the target is a few hundred KB.

## 6. Failure table

| Case | Result |
|---|---|
| Slot 404 or empty | skipped with a message |
| Event with one stored article | no cluster |
| Query copies a title | dropped (AC-3) |
| Model returns empty text | query dropped |
| All queries of a kind dropped | builder fails loudly |
| Fake-embedder run | deterministic (AC-9), no Ollama |

## 7. Security and data

Builder fetches public GDELT files over HTTPS and talks to local Ollama only; no secrets. The fixture holds real headlines and URLs, same attribution as `docs/research.md`.
