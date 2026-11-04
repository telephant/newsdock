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
**(a).** Clusters are articles that mention one event after collapsing copies by `story_key`. The fixture lives in `packages/core/tests/fixtures/` (DR-10). A setting changes only if the 95% paired-bootstrap interval of the MRR difference excludes 0, recall@5 is not lower and no kind of query is lower. A winning **prefix** is recommended, not applied: production vectors were made with the current one and the embedder re-embeds only on a model-name change.

## Consequences
+ Objective, repeatable labels without hand work; confusable by construction (same topic, different events).
+ Leave-one-out keeps the benchmark from saturating; the bootstrap keeps a handful of queries from steering defaults.
− Event labels mean "same event", not "same wording"; absolute scores are low, only relative comparison is meaningful.
− A 1B-parameter model writes the queries; weak ones are filtered by AC-3 and a human read, not fixed.
− The fixture freezes one window of the news; it ages, and a rebuild changes the numbers (backlog).
− A prefix win needs a re-embed of all vectors before it can be used.
