# Backlog — harder-search-eval

- **Body-scope eval (P2, decided 2026-11-04):** recall of `semantic_search` `scope=body|all` on the dev stack's real passages; an opt-in live command, nothing frozen (copyright, size). Overlaps body-extraction F-2.
- **A set that can test hybrid weighting (P2, from the T-05 result):** vector and hybrid tie and the sweep finds no effect of `semantic_rrf_k` or `semantic_candidates`, because the relevant articles are mostly rewordings of one headline and the full-text leg rarely fires. Add keyword-heavy and entity queries whose relevant articles share few words with the seed (for example keep only judged members with low word overlap), then rerun the sweep.
- **Human-written queries (P3):** replace or extend the model paraphrases with queries written by the owner, if the model's queries prove weak.
- **Graded relevance (P3):** weight clusters by `num_mentions` instead of the 0/1 label.
- **Hybrid weighting (P3):** if the noise measure shows keyword hits displacing good vector hits, try a weighted fusion; a search-code change, so a spec of its own.
- **Rebuild automation (P3):** a CI or scheduled rebuild of the fixture from fresh slots.
