# Backlog — hybrid-eval-set

- **Weighted or alternative fusion (P2, only if the result asks):** if entity queries show keyword hits displacing or missing good vector hits, try a weighted fusion or an OR-style keyword leg; a search-code change, so a spec of its own.
- **Full-text query semantics (P3):** `websearch_to_tsquery` ANDs all words, so long queries rarely match; an OR or "most words" mode would change what hybrid can add. Out of scope here, noted by the measurement.
- **Better name extraction (P3):** a NER model instead of capitalised words, if the heuristic proves noisy.
- **Larger, fresher corpus (P3):** rebuild with more slots when the numbers should cover more news; the two datasets then stop being comparable.
- **Body-scope eval (P2):** still the live check from harder-search-eval.
- **More queries where the keyword leg matters (P3, from the T-05 result):** hybrid differs from vector on only 7 of 74 queries; entity queries from a better name recogniser, or a few hundred more clusters, would narrow the intervals before any fusion change is argued.
