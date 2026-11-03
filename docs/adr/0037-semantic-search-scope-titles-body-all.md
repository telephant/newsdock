# ADR-0037: `semantic_search` scope: titles, body, all

Status: **Accepted 2026-11-02** (spec `body-extraction`, D-5; confirmed by the user during `/spec-design`)

## Context
`semantic_search` fuses a title vector leg and a title keyword leg by reciprocal rank (ADR-0025). The owner asked to use the content embeddings for a more accurate search (D-5). About a third of articles will have no usable body (robots, 451/403, stubs, JavaScript pages), and bodies arrive minutes to hours after the title. `fuse()` already accepts any number of named legs and `matched_by`, `score` and `degraded` exist on the result.

## Options
- **(a) New argument `scope` = `titles` | `body` | `all` on the same tool; `all` fuses four legs (title vector and keyword, passage vector and keyword); result gains `passage`; default `titles`, switchable by a setting.**
- **(b) A separate tool `search_text`.** Clear for prompts, but duplicates arguments, filters and errors, and cannot fuse with titles.
- **(c) Change the default behaviour now (always fuse bodies).** Most accurate immediately, but alters results for current callers and has no measure yet.

## Decision
**(a)**. `titles` = today's behaviour and byte-identical payload (AC-13). `body` = passage legs only, results carry the best matching `passage`. `all` = title legs plus passage legs; an article without a body is still found through its title. `matched_by` values: `vector`, `keyword`, `body_vector`, `body_keyword`. Errors: `invalid_scope`; `embedding_unavailable` and `degraded` keep their meaning for every scope. The default is the setting `api.semantic_default_scope` (`titles`); the backlog flips it to `all` once an evaluation set shows it is better.

## Consequences
+ One tool, same filters (`apply_filters` on a join to `articles`), modes and errors; titles callers unaffected.
+ Articles with and without bodies compete in one ranking; the passage is the evidence an agent can read.
− `all` costs two more queries per call (HNSW and full-text on passages); `semantic_passage_candidates` bounds it.
− Reciprocal-rank fusion weighs the four legs equally; whether `all` beats `titles` is unmeasured (needs the evaluation set).
− Four leg names and a `passage` field are new vocabulary in `CLAUDE.md` fixed names.
