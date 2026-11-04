# Design detail — harder-search-eval

Reference only; not required reading for approval.

## 1. Builder (C-90)

Inputs: `--slots N` (consecutive 15-minute slots ending at a given slot, default chosen until enough clusters, see §5), `--distractors M`, `--out` directory, Ollama URL and chat model.

Steps (pure functions first, I/O last):

1. `parse_slot(gkg_text, mentions_text, slot)` → articles (`newsdock_core.gkg.parse_row`) and mentions (`newsdock_core.mentions.parse_mention_row`); bad rows dropped.
2. `collapse(articles)` → one article per `story_key` (first by id), so syndicated copies are one.
3. `derive_clusters(articles, mentions)` → `{event_id: [article ids]}` for events whose collapsed members number 2 or more. An article appears in every cluster whose event it mentions.
3b. `drop_roundups(clusters, max_events=3)` → removes from every cluster the articles that appear in more than `max_events` clusters (roundup pieces that mention many events and blur the labels), then drops clusters left with fewer than 2 articles and duplicates of the same member set. `derive_clusters` stays exact (spec AC-2); this is a separate, explicit step. Added at T-01 from measurement; the threshold 3 is a starting value **[assumption]**.
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

**Spike result (T-01, 2026-11-04) [verified]:** 8 consecutive slots (`20261104070000`…`084500`), 8 of 8 downloads valid (the earlier empty files came from a bare `curl -O` without redirects). 10,514 articles, 28,697 mentions; 7,122 articles after collapsing by `story_key`; 1,697 events with 2 or more collapsed articles, 1,101 distinct member sets, 568 articles in 3 or more clusters (up to 53: roundups). After `drop_roundups(max_events=3)`: 580 distinct clusters over 1,281 articles (size 2: 367, 3: 100, 4: 47, 5+: 66). Sampled clusters are real confusable stories (several US midterm races, a Delhi extortion case). Cluster members alone are about 0.43 MB of JSON before distractors, so the corpus should use a smaller distractor sample, or titles only, to stay near the target. 8 slots are enough.

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
