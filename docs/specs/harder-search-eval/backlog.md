# Backlog — harder-search-eval

- **Body-scope eval (P2, decided 2026-11-04):** recall of `semantic_search` `scope=body|all` on the dev stack's real passages; an opt-in live command, nothing frozen (copyright, size). Overlaps body-extraction F-2.
- **Human-written queries (P3):** replace or extend the model paraphrases with queries written by the owner, if the model's queries prove weak.
- **Graded relevance (P3):** weight clusters by `num_mentions` instead of the 0/1 label.
- **Hybrid weighting (P3):** if the noise measure shows keyword hits displacing good vector hits, try a weighted fusion; a search-code change, so a spec of its own.
- **Rebuild automation (P3):** a CI or scheduled rebuild of the fixture from fresh slots.
