# Design — hybrid-eval-set (M3g)

Reading order: this file → `diagrams/index.html` (components, sequence, data) → `design-detail.md` (reference only). No new ADR: this extends ADR-0039 (see the last checklist question).

## Idea

Reuse the frozen corpus and add a **hard-queries file** made offline from the frozen files. Two kinds of query test what the first set could not: `entity` queries (2 to 3 proper names from the seed title, where exact words matter and the full-text leg can fire) and `lowoverlap` queries (the existing paraphrase queries graded only on relevant members that share under half their words with the seed). The harness gets a new dataset `events-hard`, removes ignored members from result lists like the seed, and reruns report, noise and sweep.

## Components (ids continue from M3f)

| Id | Job | Where |
|---|---|---|
| C-94 hard builder | reads `search_eval_corpus.json` and `search_eval_queries.json`, extracts names, grades members, writes `search_eval_hard_queries.json`; pure functions plus a thin file wrapper, no network, no model; `make eval-search-build-hard` | `infra/scripts/search_eval_build.py` (functions), `infra/scripts/build_search_eval_hard.py` (wrapper) |
| C-95 hard fixture | the generated queries file (tens of KB) | `packages/core/tests/fixtures/search_eval_hard_queries.json` |
| C-92 harness (extended) | dataset `events-hard`; `ignore` list per query; scoring leaves out the seed and the ignored members; report and sweep unchanged | `apps/api/tests/eval/search_eval_harness.py`, `test_search_eval.py` |
| C-93 report | ADR-0039 Result section gets the M3g numbers and decision | docs |

Nothing in the platform changes; the old datasets and files stay byte-identical.

## Key flows

1. **Build (offline, instant):** read frozen files → names per seed → entity queries; members graded by word overlap → low-overlap queries → check → write file (diagram 2).
2. **Run:** `events-hard` through the four methods, drop seed and ignored ids, score by kind, noise, sweep (diagram 2).
3. **Decide:** the existing bootstrap rule on the new rows; the result goes in ADR-0039.

## Contracts

| Item | Shape |
|---|---|
| Hard query row | `{query, kind ("entity" or "lowoverlap"), cluster, seed, members, expected (graded), ignore (ids)}`; `members` = cluster incl. seed; `expected` and `ignore` are disjoint and together equal `members` minus the seed |
| Entity query | the 2 or 3 names joined by a space, in title order |
| Low-overlap query | the text of the cluster's existing `paraphrase` query; graded = relevant members with word overlap < 0.5 with the seed |
| Scoring | `without(ids, {seed} ∪ ignore, k=5)` then recall@5 and MRR as before |
| Word overlap | the shared-significant-words measure of `search_eval_build.word_overlap` (words over 3 letters, lower-cased, over the smaller title's count) |

## Tricky parts

- **Names from titles:** capitalised words are a stand-in for proper names; the extractor cuts the outlet suffix (` | Outlet`), HTML entities and punctuation, skips sentence-initial words and a small stoplist of title-case verbs (`Wins`, `Four`, `What's`), keeps acronyms, at most 3 names. It is tuned on the frozen seeds at implementation and the result is read by eye.
- **Ignored members:** a low-overlap query is graded on the hard members only; the near-duplicate relevant members would otherwise outrank them and count as wrong. They are removed from the lists, never added to the negatives.
- **Same rules as before:** entity and low-overlap query texts must pass `query_ok` against all corpus titles and be unique per kind.
- **Honest tie:** if vector and hybrid still tie, that is recorded as the result (spec D-5).

## Failure modes

| Failure | Effect |
|---|---|
| Seed title yields fewer than 2 names | no entity query for that cluster |
| Cluster with no low-overlap member | no low-overlap query |
| Entity query equals or sits inside a title | dropped |
| Frozen files missing | the builder stops with a message (they are committed) |
| Too few hard queries | the builder reports the count; the harness still runs (wide intervals) |

## Technology

Python stdlib (`re`, `json`), the existing builder module and harness. No new dependency, no network, no model call.

## AC coverage

| AC | Where |
|---|---|
| AC-1 | C-94 `extract_names` |
| AC-2, AC-4 | C-94 `check_hard_fixture`, C-95 |
| AC-3 | C-94 `grade_members` |
| AC-5 | C-94 wrapper (no I/O besides the files, deterministic) |
| AC-6 | C-92 `without` |
| AC-7, AC-9 | C-92 dataset `events-hard`, report, sweep |
| AC-8, AC-10 | C-93 real-model run and ADR-0039 Result (manual) |
| AC-11 | `make config-python` |
| AC-12 | `git diff` of the earlier fixtures and `apps/*/src` (manual) |

## Questions to answer before approving this design

- [x] Extend ADR-0039 with a short "M3g" section (no new ADR) instead of a new ADR?
- [x] Entity queries are names only (no verbs), cut from the seed title by a heuristic that is tuned on the frozen seeds and read by eye?
- [x] Ignored members are removed from result lists (neither hit nor miss), as the seed is?
- [x] The new queries live in their own file, so the two earlier datasets stay untouched?
