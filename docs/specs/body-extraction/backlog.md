# Backlog — body-extraction

Later items, one line each (P1 highest).

- **Retrieval-quality evaluation (P2):** an evaluation set for text search (recall@k and MRR, like `make eval-search` for titles) so passage size, overlap and hybrid weights can be tuned on data. Why: the 40-title set was already called too easy; text search has no measure yet. Since 2026-11-04 it also gates `embedder.embed_passages` (ADR-0036 amendment): passage vectors stay off until they measurably beat the passages' keyword leg.
- **Make `scope=all` the default (P2):** flip `api.semantic_default_scope` once the evaluation set shows fused title-and-text search beats titles. Why: the owner wants the most accurate search; the default stays `titles` until it is measured.
- **Fetch copies and refresh (P2):** also fetch the copies in `article_sources` when the canonical fails, and refetch a body that changed. Why: some canonicals are blocked while a copy on another site is not.
- **Digest agent reads bodies (P2): done 2026-11-04.** `agents/whathappen` now grounds each listed story's sentence in the stored text (`get_article`, `WHATHAPPEN_SUMMARY_BODY_CHARS`), falling back to headlines when none is stored. Why it existed: the owner judged the title-only summaries poor (`digest-top-stories` verify F-8).
- **JavaScript-rendered pages (P3):** a headless-browser fallback for pages that return no text. Why: part of the "no text" and "too short" share; costly and heavier to run politely.
- **Paywall and consent pages (P3):** detect and label them instead of storing a stub. Why: 2 of 28 fetched pages were short stubs.
- **PDF and other formats (P3):** extract text from linked PDFs. Why: some press releases and reports are PDFs.
- **Isolate the extractor on a `crawl` network (P2, ADR-0034):** attach it to a network shared only with Postgres so it cannot reach Kafka or the workers. Why: the owner chose the existing `data` network, so the address guard is the only wall against SSRF; a network wall would back it up.
- **Smaller vectors (P3):** fewer or shorter passages, or a smaller model, if the live size is too large (`halfvec` is already chosen, ADR-0036). Why: storage is the main cost.
- **Language filter or multilingual model (P3):** many sites are not English. Why: `nomic-embed-text` is English-biased.
- **Event and body together (P3):** combine `include=events` and body passages in one answer, for example the passage that mentions an event. Why: both are now per-article extras.
- **Per-site fetch statistics screen (P3):** which sites block us and how often. Why: the operator sees only counts today.
- **Read the live measurements (P2, verify F-2):** M-1…M-7 after a day on the live stack (AC-16 itself passed on 2026-11-03; only the first minutes were read). Why: size and `ok` share are estimates from the T-01 spike and a first reading.
