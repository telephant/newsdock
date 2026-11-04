# ADR-0039: Search eval labelled by GDELT events, scored leave-one-out, settings chosen by a paired bootstrap

Status: **Accepted 2026-11-04** (confirmed by the user during `/spec-design`; spec `harder-search-eval`, D-1 to D-6).

## Context
The 40-title hand-labelled eval scores 1.000 for vector and hybrid, so it cannot choose the title prefix, `semantic_rrf_k` or `semantic_candidates` (semantic-search verify F-5/F-6). Real data are available: GDELT Events and Mentions say which articles are about the same event (M3c). One slot has 83 events with 2 or more different titles; one slot is too thin (spec §3).

## Options
- **(a) Event-labelled real titles, queries by a local model, seed removed from results (leave-one-out), settings picked by a paired bootstrap over queries.**
- **(b) Hand-written confusable set** (more topics by the same author): controlled, small, same author for labels and queries.
- **(c) Score without leave-one-out:** simpler, but a paraphrase of a title finds that title, so methods saturate again.
- **(d) Pick settings by the highest mean:** no noise handling; a few queries decide.

## Decision
**(a).** Clusters are articles that mention one event after collapsing copies by `story_key`; **amended 2026-11-04 (measured at T-03)**: GDELT's event links join unrelated articles even at confidence 100 (a Kerala politics story linked to a Newcastle shop worker), so these clusters are only candidates and each member is kept only if a local model (`llama3.2:3b`, not the embedder) judges it about the same story as the seed; every judgment is logged, and rejected candidates stay in the corpus as hard negatives. The user chose this over "2+ shared events" and "raw labels". The fixture lives in `packages/core/tests/fixtures/` (DR-10). A setting changes only if the 95% paired-bootstrap interval of the MRR difference excludes 0, recall@5 is not lower and no kind of query is lower. A winning **prefix** is recommended, not applied: production vectors were made with the current one and the embedder re-embeds only on a model-name change.

**Clean-up rules (T-03, 2026-11-04):** a rejected candidate whose title shares 80% or more of the significant words with the seed is left out of the corpus (the judge often refuses near-identical headlines, so it is ambiguous, not a negative); one cluster per seed; one query text per kind. Measured: the judge said yes to 95 of 1,119 pairs; 73 clusters and 146 queries remain.

## M3g extension (2026-11-04, spec `hybrid-eval-set`, approved by the user during `/spec-design`)

The first result left vector and hybrid tied: the full-text leg ANDs every query word, so paraphrases rarely match it, and most relevant articles reword one headline. A second query set over the same frozen corpus tests what that one could not: `entity` queries (2 to 3 proper names cut from the seed title, so exact words matter) and `lowoverlap` queries (the existing paraphrase queries graded only on relevant members sharing under half their words with the seed). Relevant members that are not graded are **ignored**: removed from the result lists like the seed, so they neither count as hits nor as wrong. The set lives in its own file (`search_eval_hard_queries.json`), built offline by `make eval-search-build-hard`; the earlier fixtures stay byte-identical. A tie between vector and hybrid on this set is recorded as a finding and the defaults stay.

## Result (2026-11-04, real model `nomic-embed-text`, `events` dataset: 146 queries, 1,557 articles)

| Method | recall@5 | MRR |
|---|---|---|
| keyword (substring, `search_articles`) | 0.000 | 0.000 |
| fulltext (hybrid's keyword leg) | 0.103 | 0.099 |
| vector | 0.764 | 0.660 |
| hybrid | 0.764 | 0.660 |

The set separates keyword and full-text from vector (the old 40-title set scored vector and hybrid 1.000 and still does). Vector and hybrid tie. Hybrid noise (F-6): of 120 relevant vector top-5 hits, hybrid dropped 0; keyword noise did not displace vector hits at this scale, because the full-text leg rarely fires (16 relevant hits in total).

Sweep (24 rows, prefix on/off × `semantic_rrf_k` 10/30/60/100 × `semantic_candidates` 20/50/100): every `rrf_k` and `candidates` row is identical (vector and hybrid only see their top 5 and the full-text leg is too weak to reorder them); without prefixes vector is 0.768 / 0.645 and hybrid 0.765 / 0.651. **Clear wins over the defaults under the bootstrap rule: 0.**

Decision per setting (nothing changed): **prefix: kept** (`search_document: ` / `search_query: `; on is slightly better on MRR, not a clear win either way); **`semantic_rrf_k`: kept at 60**; **`semantic_candidates`: kept at 50**. The numbers cannot tell these settings apart, which is a statement about this set, not a proof that they do not matter: the relevant articles are mostly rewordings of one headline (the judge keeps near-duplicates), so vector search finds them alike under any setting. A set with more keyword-heavy and entity queries would be needed to test the hybrid weighting (backlog of `harder-search-eval`).

## Consequences
+ Objective, repeatable labels without hand work; confusable by construction (same topic, different events).
+ Leave-one-out keeps the benchmark from saturating; the bootstrap keeps a handful of queries from steering defaults.
− Labels are GDELT candidates filtered by a small model: absolute scores mean little, only relative comparison is meaningful, and a judge that likes similar wording can favour methods that match wording.
− A 1B-parameter model writes the queries; weak ones are filtered by AC-3 and a human read, not fixed.
− The fixture freezes one window of the news; it ages, and a rebuild changes the numbers (backlog).
− A prefix win needs a re-embed of all vectors before it can be used.
