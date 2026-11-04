# Design detail — hybrid-eval-set

Reference only; not required reading for approval.

## 1. Builder functions (`infra/scripts/search_eval_build.py`, pure)

- `extract_names(title: str, *, limit: int = 3) -> list[str]`:
  1. unescape HTML entities and cut the title at the first ` | ` and at a trailing ` - Outlet`;
  2. split on whitespace; strip surrounding punctuation (`.,:;!?"'()` and dashes);
  3. a token is a name if it starts with an upper-case letter and has 3 or more letters, or is an all-caps acronym of 2 or more letters;
  4. skip a token that is the first of the title or follows a token ending in `. ? ! :`, and any token in `TITLE_WORDS` (a small constant of title-case non-names such as `Wins`, `Win`, `Four`, `What's`, `Just`, `Live`, `Updates`, `Breaking`; a starting list **[assumption]**, tuned on the frozen seeds);
  5. keep distinct tokens in title order, at most `limit`.
- `grade_members(seed_title, members, titles, *, threshold=0.5) -> tuple[list[str], list[str]]`: for each relevant member (the cluster without the seed) compute `word_overlap(seed_title, titles[m])`; graded = below `threshold`, ignored = the rest. Threshold 0.5 is a starting value **[assumption]**.
- `build_hard_queries(corpus, queries) -> list[dict]`: group the frozen queries by cluster; for each cluster (seed from the queries): an `entity` query if `extract_names(seed title)` has 2 or more names (text = names joined by a space), and a `lowoverlap` query if `grade_members` returns a graded member (text = that cluster's `paraphrase` query text, expected = graded, ignore = ignored). Texts failing `query_ok` against all corpus titles, or repeated within a kind, are dropped; output is sorted by (kind, cluster).
- `check_hard_fixture(corpus, queries)`: ids exist in the corpus; `expected` and `ignore` disjoint; both subsets of `members` minus the seed; their union equals that set for `lowoverlap` and `expected` equals it for `entity`; every `entity` query has 2 or more names (words) and no text is empty, a title or inside a title; no text repeats within a kind.

## 2. Wrapper (`infra/scripts/build_search_eval_hard.py`)

Reads the two frozen files from `packages/core/tests/fixtures/`, calls `build_hard_queries` and `check_hard_fixture`, writes `search_eval_hard_queries.json` as `{"built": {...}, "queries": [...]}` (one query per line, like the other fixture), prints the counts per kind. No `urllib`, no `subprocess`, no clock in the output (the `built` header has the source file names, not a date) so two runs give identical bytes.

## 3. Harness changes

- `Dataset.queries` rows get `ignore` (list, empty for `easy` and `events`).
- `without(ids, drop, *, k=5)` removes any id in `drop` then keeps k; `without_seed(ids, seed, k)` stays as a thin wrapper for the existing tests.
- `run_queries` drops `{seed} ∪ ignore` from every method's list.
- `load_dataset("events-hard")`: corpus from `search_eval_corpus.json`, queries from `search_eval_hard_queries.json`.
- Report and sweep need no change: they already group by `kind`. The real-model tests run `events-hard` next to `events`.

## 4. Failure table

| Case | Result |
|---|---|
| Seed title with no capitalised word | no entity query |
| Two clusters give the same entity text | the first (lowest cluster id) keeps it |
| All members high-overlap | no low-overlap query for that cluster |
| Seed id missing from corpus | builder error (frozen files are inconsistent) |

## 5. Security and data

Offline, deterministic, reads and writes files in `packages/core/tests/fixtures/` only; the fixture holds the same real headlines as the frozen corpus.
