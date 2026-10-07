# dedup-syndication — Design detail

**Reference only. Not required reading for design approval.** Overview: [design.md](design.md).

## 1. Schema delta (Alembic revision `0003`, forward-only, no backfill)

```sql
ALTER TABLE articles ADD COLUMN story_key text NULL;  -- NULL = pre-feature row
CREATE INDEX ix_articles_story_key_published_at ON articles (story_key, published_at);

CREATE TABLE article_sources (
  url_hash      text PRIMARY KEY,              -- sha256 of the copy's normalized URL
  article_id    text NOT NULL REFERENCES articles(url_hash) ON DELETE CASCADE,
  url           text NOT NULL,
  domain        text,
  slot          text NOT NULL,
  gkg_record_id text NOT NULL,
  published_at  timestamptz NOT NULL,
  ingested_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_article_sources_article_id ON article_sources (article_id);

GRANT SELECT, INSERT, DELETE ON article_sources TO sink_rw;
GRANT SELECT ON article_sources TO api_rw;
```

ORM: `ArticleSource` mapped class in `newsdock_db.models`; `Article.story_key` added. TC-34-style autogenerate no-op test extends to the new table.

## 2. Algorithms

**Story key (C-10, `newsdock_core.stories.story_key`).** Pure, deterministic:
1. `unicodedata.normalize("NFKC", title)`, lowercase, collapse all whitespace runs to one space, strip.
2. Fixpoint suffix strip (max 3 iterations): if the title matches `^(?P<rest>.{25,})\s[|\-–—]\s(?P<seg>.{1,45})$` → keep `rest`, repeat. The 25/45 thresholds keep real headline dashes ("Movie Review - Crushed" has rest < 25 or seg > 45 in practice) while catching `… | Wilts and Gloucestershire Standard` and `… - BusinessWorld Online` (both observed in real data).
3. Empty result (defensive) → fall back to the unstripped normalized title.
All copies of a story converge: `key("T | SiteA") → key("T")` because stripping runs to a fixpoint on both inputs.

**Sink grouping (C-4).** Replaces the plain batch upsert; still one writer, still at-least-once:
```
for each CleanArticle in batch (in offset order):
    key = story_key(title)
    canonical = in-batch cache hit
             or SELECT url_hash, published_at FROM articles
                WHERE story_key = :key
                  AND published_at BETWEEN :p - WINDOW AND :p + WINDOW
                ORDER BY published_at LIMIT 1
    if canonical is None:
        INSERT INTO articles (..., story_key) ON CONFLICT (url_hash) DO NOTHING
        canonical = this article (if conflict: the existing row with this url_hash)
    INSERT INTO article_sources (url_hash, article_id, ...) ON CONFLICT DO NOTHING
    cache[key within window] = canonical
commit; then commit Kafka offsets
log: "dedup: %d canonicals, %d grouped copies, %d url-duplicates" (AC-12)
```
Poison fallback, DbUnavailable backoff and the dlq path stay exactly as in M1 (row-by-row on batch failure).
`WINDOW` = `NEWSDOCK_STORY_WINDOW_HOURS` (default 48), read in `config.py` only.

**Retention.** Unchanged query on `articles.ingested_at`; `article_sources` go via `ON DELETE CASCADE` (AC-11).

## 3. API deltas (C-6)

| Surface | Change |
|---|---|
| summary (search/list/feed) | `+ source_count` — `COUNT(article_sources)` per returned article, `max(count, 1)` so pre-feature rows read as 1 |
| `get_article` / `GET /api/articles/{id}` | `+ sources: [{url, domain, published_at}]` ordered by `published_at`, `+ source_count` |
| OpenAPI / web types | regenerate `apps/web/src/lib/api/types.ts` (additive) |

Counts are fetched with one grouped query per page (same pattern as the scores map), not per row.

## 4. UI (C-8)

Feed item: badge `· N sites` when `source_count > 1`. Detail: "Seen on N sites" section listing `domain — url` links (`rel="noreferrer noopener"`, text rendered escaped as everywhere else).

## 5. Failure table (delta)

| Failure | Detection | Handling |
|---|---|---|
| Two batches, same story, crash between | redelivery | second pass: canonical lookup hits, source insert conflicts → no-op |
| Canonical row conflict (same url_hash re-sent as "new story") | ON CONFLICT DO NOTHING returns no row | re-read by url_hash and continue as existing canonical |
| False merge discovered later | manual | repair job is backlog ("Merge repair"); sources keep every copy's data so nothing is lost |
| Clock skew between copies' published_at | window too tight | window is config; verify measures observed spreads |

## 6. Security

No new surfaces. Source URLs render as escaped text/links in the UI (same XSS stance as payloads); `sources[]` adds no new write path; `article_sources` grants follow least privilege (§1).

## 7. Observability for verify

The AC-12 log line gives per-batch `canonicals / grouped copies / url-duplicates`; verify sums it over a live slot to report the measured reduction (provisional target ≈ 14 %).
