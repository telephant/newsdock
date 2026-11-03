# Design detail — events-mentions

Reference only; not required reading to approve the design. Summary: [design.md](design.md).

## 1. Column maps (1-based, from GDELT 2.0 codebook **[memory]**, confirmed on real rows 2026-11-02 **[verified]** for the columns marked ✓)

Events (61): 1 `GLOBALEVENTID` ✓, 2 `SQLDATE` ✓ (YYYYMMDD), 6 Actor1Code, 7 Actor1Name, 8 Actor1CountryCode, 13 Actor1Type1Code, 16 Actor2Code ✓, 17 Actor2Name ✓, 18 Actor2CountryCode ✓, 23 Actor2Type1Code, 26 IsRootEvent ✓, 27 EventCode ✓, 28 EventBaseCode ✓, 29 EventRootCode ✓, 30 QuadClass ✓, 31 GoldsteinScale ✓, 32 NumMentions ✓, 33 NumSources ✓, 34 NumArticles ✓, 35 AvgTone ✓, 52 ActionGeo_Type, 53 ActionGeo_FullName ✓, 54 ActionGeo_CountryCode ✓, 55 ActionGeo_ADM1Code ✓, 57 ActionGeo_Lat ✓, 58 ActionGeo_Long ✓, 60 DATEADDED ✓ (YYYYMMDDHHMMSS), 61 SOURCEURL ✓. Columns 44–51 are Actor2Geo; 36–43 Actor1Geo. The parser reads by index from one table of constants in `newsdock_core.events`; the design spike of the plan re-verifies the map on 3 more slots before the fixture is frozen.

Mentions (16): 1 `GLOBALEVENTID`, 2 EventTimeDate, 3 MentionTimeDate (YYYYMMDDHHMMSS), 4 MentionType, 5 MentionSourceName, 6 MentionIdentifier (URL), 12 Confidence (0–100, may be empty), 14 MentionDocTone. Others ignored.

### Spike result (T-01, 2026-11-02) **[verified]**

Checked six slots in all (`20261102110000` and `…120000` earlier, plus `20261102060000`, `…090000`, `20261101180000`, `20261101000000`, `20261031123000`; the last five this task):

- Every Events row has 61 columns (about 5,000 rows) and every Mentions row has 16 (about 10,800 rows); `MentionType` is always `1`.
- Every row passes the per-column checks the parser will rely on: event id numeric, `SQLDATE` 8 digits, `IsRootEvent` 0/1, CAMEO codes non-empty, `QuadClass` 1–4, Goldstein and counts numeric, `AvgTone` present and numeric (never empty), lat/long numeric or empty, `DATEADDED` 14 digits, `SOURCEURL` starts with `http`, mention time 14 digits, mention URL starts with `http`, `Confidence` numeric.
- Empty values that are normal and must not be rejected: Actor1 name (about 8–11% of rows), Actor2 name (about 27–32%), action geo name (about 2–4%), lat/long (rare). `Confidence` was never empty in these slots, so the empty-confidence case is covered by a hand-made row.
- Spot check on real rows confirms the column map above: Actor2 at columns 16–23, ActionGeo at 52–59 (type, name, country, ADM1, ADM2, lat, long, feature id), `DATEADDED` at 60 and `SOURCEURL` at 61. Lat and long can be integers (`13`, `-2`).
- Join facts: an event's `SOURCEURL` is among the mentions of the same event in 100% of events in every slot (911/911, 966/966, 1107/1107, 1132/1132, 735/735, 996/996). Event URLs found in the same slot's GKG: 99.4–100% (one URL missing in three slots). Mention URLs found in the GKG: 99.6–100%. Repeated (event, URL) mention rows per slot: 0–53.
- An event can carry an old `SQLDATE` (for example `20261026` added at `20261102110000`); the parser keeps `SQLDATE` and `DATEADDED` as two fields.
- Not covered: GDELT redistribution terms (still the open item in `docs/research.md`).

Fixtures frozen in `packages/core/tests/fixtures/`: `events_sample.tsv` (33 rows of slot `20261102110000`: no actor 1, no actor 2, no geo, old `SQLDATE`, missing lat/long), `mentions_sample.tsv` (60 rows, starting with one repeated (event, URL) pair), `bad_event_rows.json` (8 cases) and `bad_mention_rows.json` (7 cases) in the `name` / `expect` / `line` shape of `bad_rows.json`. The `expected_*.json` files are written test-first in T-02 (hand-checked against these rows), not here.

## 2. Messages (`newsdock_core.contracts`)

```
RawMessage     {slot, row_no, line, kind: "gkg"|"events"|"mentions" = "gkg"}
CleanEvent     {event_id:int, event_date:date, actor1:Actor, actor2:Actor, is_root:bool,
                cameo_code, cameo_base, cameo_root, quad_class:int|None, goldstein:float|None,
                num_mentions:int, num_sources:int, num_articles:int, avg_tone:float|None,
                geo:Geo|None, date_added:datetime, source_url, source_url_hash}
Actor          {code, name, country, type1}   (all str|None)
Geo            {name, country, adm1, lat:float|None, lon:float|None}
CleanMention   {event_id:int, url, url_hash, source_name, mention_time:datetime, confidence:int|None}
DlqMessage     existing + kind (default "gkg"); DlqReason += missing_event_id
```

Validation: Events — 61 columns (`bad_column_count`), non-empty numeric id (`missing_event_id`), non-empty `SOURCEURL` (`missing_url`), dates/numbers parse (`bad_field`). Mentions — 16 columns, numeric event id (`missing_event_id`), non-empty URL (`missing_url`), mention time parses (`bad_field`). Empty actors, geo and tone are normal. The key reasons from CLAUDE.md are only extended, never renamed.

## 3. Ingester

- `domain/index.py`: `parse_lastupdate` returns one `IndexEntry(slot, kind, md5, url)` per recognised line (`gkg.csv.zip`, `export.CSV.zip`, `mentions.CSV.zip`). The existing GKG behaviour is kept by a wrapper.
- `ingest_file(slot, kind, status, attempts, row_count, updated_at)`, PK `(slot, kind)`, kinds `events` and `mentions` only. A cycle: GKG as today, then for each pending `ingest_file` row (`attempts < max_attempts`) fetch → md5 (when the index entry is current) → publish with `kind` → `published`.
- A file row is created when the index lists it; it never gates the GKG slot status. No back-fill of slots missed while the feature was off (decided 2026-11-02): only slots first listed after the deploy get file rows.
- `GdeltSource.fetch(url)` generalises `fetch_gkg`; `url_for(slot, kind)`.
- Publisher: `KafkaRawPublisher` gets the `kind` field set on the message; the topic is still `kafka_topics_raw`.
- New settings (ingester): `fetch_events` (true), `fetch_mentions` (true). Switching both off restores today's behaviour.

## 4. Processor

`route(message)` dispatches on `message.kind`: `gkg` → `parse_row` (unchanged), `events` → `parse_event_row`, `mentions` → `parse_mention_row`. `Routed` gains nothing; the topic is chosen from settings `kafka_topics_events_clean`, `kafka_topics_mentions_clean`. `ensure_topics` creates five topics. New settings are added to the processor and the sink, with the yaml `common.kafka.topics` block extended; `check_config.py` banned-literal list gets `events.clean` and `mentions.clean`.

## 5. Sink

- `KafkaSinkLoop` subscribes to the three clean topics (the two new ones only when it is given a `GdeltWriter`); the loop itself splits the polled messages by topic, calls `process_batch` for articles and `process_events` / `process_mentions` (pure logic in `domain/gdelt.py`) for the others. Offsets are committed after all three succeed (at-least-once). A message the sink dead-letters keeps its Kafka key (`event_id`, or `event_id:url_hash`) and has `row_no = -1` and `slot = "unknown"`, as for articles; only the processor's dead letters use `slot:row_no`.
- Events upsert:

```sql
INSERT INTO events (...) VALUES (...)
ON CONFLICT (event_id) DO UPDATE SET <all curated columns>, ingested_at = now()
WHERE excluded.date_added >= events.date_added
```
- Mentions upsert: `ON CONFLICT (event_id, url_hash) DO UPDATE SET confidence = excluded.confidence, mention_time = excluded.mention_time WHERE excluded.mention_time >= mentions.mention_time`.
- Batches are deduplicated in memory by key (last one wins) before the statement, because Postgres refuses an `ON CONFLICT DO UPDATE` that touches the same row twice (this is the 53-in-one-slot case).
- Retention: `SqlGdeltWriter.delete_ingested_before(cutoff)` runs `DELETE FROM events/mentions WHERE ingested_at < :cutoff` and returns both counts; `__main__` calls it right after the articles delete with the same cutoff, so the same `retention_days` applies.

## 6. Schema (migration `0011_events_mentions`, additive)

Implemented in T-04 (2026-11-02). One deviation from the first sketch below: hash columns are `text`, not `char(64)`, to match `articles.url_hash`; `kind` has the named check `ck_ingest_file_kind`; models are `Event`, `Mention`, `IngestFile` in `newsdock_db.models`.

```
events(event_id bigint PK, event_date date NOT NULL, is_root bool,
  actor1_code text, actor1_name text, actor1_country text, actor1_type text,
  actor2_code text, actor2_name text, actor2_country text, actor2_type text,
  cameo_code text, cameo_base text, cameo_root text, quad_class smallint,
  goldstein real, num_mentions int, num_sources int, num_articles int, avg_tone real,
  geo_name text, geo_country text, geo_adm1 text, geo_lat double precision, geo_lon double precision,
  date_added timestamptz NOT NULL, source_url text NOT NULL, source_url_hash text NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now())
  idx ix_events_ingested_at (ingested_at), ix_events_source_url_hash (source_url_hash)
mentions(event_id bigint, url_hash text, url text NOT NULL, source_name text,
  mention_time timestamptz NOT NULL, confidence smallint,
  ingested_at timestamptz NOT NULL DEFAULT now(), PK (event_id, url_hash))
  idx ix_mentions_url_hash (url_hash, event_id), ix_mentions_ingested_at (ingested_at)
ingest_file(slot text, kind text CHECK kind IN ('events','mentions'), status text, attempts int DEFAULT 0,
  row_count int, updated_at timestamptz DEFAULT now(), PK (slot, kind))
```

Grants: `ingester_rw` SELECT/INSERT/UPDATE on `ingest_file`; `sink_rw` SELECT/INSERT/UPDATE/DELETE on `events`, `mentions`; `api_rw` SELECT on `events`, `mentions`. Models are added to `newsdock_db.models` (the autogenerate no-op test must stay green). No sequences are involved. Size estimate (spec §3, **[assumption]**): 0.7 M events × ~400 B + 1.7 M mentions × ~250 B ≈ 0.7 GB plus indexes for 7 days; checked in AC-14.

## 7. API

- (Implemented in T-08, 2026-11-02; `tone.py` re-exports `parse_include`, `InvalidInclude` and `TONE_FIELDS` so existing imports work; the event JSON field is `date`, as written below; `events_per_article` is an `api` setting and the repo takes it as `events_per_article=`.) `domain/include.py` (new, replacing the tuple check in `tone.py`): `INCLUDE_NAMES = TONE_FIELDS + ("events",)`; `parse_include` unchanged in behaviour and error (`InvalidInclude`). Tone code that iterates the tuple keeps working because it filters on its own subset.
- `ArticleSummary` gets `events: list[EventOut] | None = Field(default=None, exclude=True)`; `to_json(include)` adds `events` (list, `[]` when none) only when requested; `ArticleDetail` always carries `events`.
- Repo: `_events_for(url_hashes)` runs once per page:

```sql
SELECT m.url_hash, e.*, (SELECT count(*) FROM mentions c WHERE c.event_id = e.event_id) AS mention_count
FROM mentions m JOIN events e USING (event_id)
WHERE m.url_hash = ANY(:hashes)
```
  ordered by `num_mentions desc, event_id` in SQL and cut per article to `api.events_per_article` in Python (the count is a scalar subquery on an aliased `mentions`). The count subquery uses the `(event_id, url_hash)` primary key. `semantic_search`, `search_articles`, `list_new_articles`, `GET /api/articles` reach it through `summaries(ids, include)`/`_summary`.
- OpenAPI (done in T-09): documentation-only `ArticleSummaryEvents` and `FeedPageEvents` twins extend the tone twins (`GET /api/articles` documents `FeedPageEvents`; the web aliases in `features/feed/api.ts` point at them); `openapi.json` and `types.ts` regenerated; `test_openapi_contract.py` guards it.
- Subscriptions and SSE are unchanged (no `include`).
- Errors: unknown name → MCP `invalid_include`, REST 422 `invalid_include` (existing).

## 8. Failure table

| Failure | Effect | Handling |
|---|---|---|
| lastupdate lists no Events line | no `ingest_file` row; GKG proceeds | normal |
| md5 mismatch / bad zip / empty | `attempts += 1`, retry next cycle, `failed` at 4 | same as GKG |
| Producer or broker down | cycle fails, no commit | at-least-once |
| Row with 61 columns but junk dates | DLQ `bad_field` | counted, not stored |
| Duplicate keys in a batch | collapsed in memory before the upsert | AC-5 |
| Mention for unknown event | stored; invisible in API until the event arrives | AC-7 |
| API query slow | index `ix_mentions_url_hash`; page size is capped (existing limit) | measured in AC-14 |

## 9. Security

SQL parameterised; no new credentials; no secrets in settings. Event and actor text is untrusted: rendered as JSON data to agents, and escaped text if a UI ever shows it (existing rule). The 20-event cap bounds response size.

## 10. Extension points (backlog)

Filters on CAMEO/Goldstein/country reuse `apply_filters`; digest ranking can read `mention_count`; push can use a trigger like migration 0005.
