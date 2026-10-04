# newsdock — research notes

Evidence gathered while specifying and designing the MVP. Dates are UTC. Tags: **[verified]** = observed directly this session; **[memory]** = from recall, not checked; **[assumption]** = reasoned, not measured.

Related: `docs/specs/mvp/spec.md` §3, `docs/specs/mvp/design.md`, `docs/adr/`.

---

## 1. GDELT feed: what I tested (2026-10-04)

### 1.1 Feed index
`https://data.gdeltproject.org/gdeltv2/lastupdate.txt` lists three files for the latest 15-minute slot, one per line as `size md5 url`: **[verified]**

```
51977   8af85d9c…  http://data.gdeltproject.org/gdeltv2/20261004084500.export.CSV.zip     (Events)
44704   b5effc4b…  http://data.gdeltproject.org/gdeltv2/20261004084500.mentions.CSV.zip   (Mentions)
2339975 5f34fe50…  http://data.gdeltproject.org/gdeltv2/20261004084500.gkg.csv.zip        (GKG)
```

- The index returns `http://` URLs; `http://` redirects (301) to `https://`, so clients must follow redirects. **[verified]**
- `masterfilelist.txt` also lists the recent GKG slots (tail checked: `…080000`, `…081500`, `…083000`, `…084500`). History back to 2015-02-18 is **[memory]**, not read.

### 1.2 Availability lag (the "404 quirk")
Checked at about 08:42 UTC: **[verified]**

| Slot | Age at check | HTTP | Size |
|---|---|---|---|
| `20261004081500` | ~27 min | 200 | 2,258,114 bytes |
| `20261004083000` | ~12 min | **404** | 0 |
| `20261004084500` | listed in `lastupdate.txt` | **404** | 0 |

- A slot can be listed in the index and still return 404 with an empty body. The same thing was reproduced earlier in the spec stage (slot `…081500` was 404 at first, 200 later).
- Lag appears to be roughly 12–27 minutes. Not statistically measured. **[assumption]**
- Consequence: the ingester treats 404, empty body or md5 mismatch as "retry later" (AC-2), keeps the slot `pending`, and retries up to 4 cycles (~1 hour).

### 1.3 Slot content: `20261004081500.gkg.csv`

| Measure | Value |
|---|---|
| Rows | 527 |
| Columns per row | 27 for all 527 rows |
| Rows with empty URL (col 5) | 0 |
| Rows without `<PAGE_TITLE>` | 0 |
| Rows with empty `<PAGE_TITLE>` | 0 |
| Duplicate URLs within the slot | 0 |
| Rows with empty themes (col 8 and 9) | 86 (16%) |
| Rows with empty persons (col 12) | 109 (21%) |
| Rows with empty orgs (col 14) | 150 (28%) |
| Rows with empty tone (col 16) | 0 |
| Rows with `<PAGE_PRECISEPUBTIMESTAMP>` | 344 (65%) |
| Rows with `<PAGE_ALTURL_AMP>` | 77 (15%) |
| Rows mentioning `ECON_` or a `WB_*FINANC*` theme | 127 (24%) |
| Zipped size | 2.26 MB |

Top source domains in this slot: `iheart.com` (26), `theargus.co.uk` (19), `lankanewspapers.com` (17).

Earlier sample (spec stage): slot `20261004071500`, 342 rows, 27 columns, 1.4 MB zipped, 4.3 MB unzipped. **[verified]** Row counts therefore vary a lot by slot (342 vs 527), so any daily estimate (~30–50k rows/day, 200–350k per 7 days) is **[assumption]**.

### 1.4 Not yet measured
- Cross-slot duplicate rate (how often the same URL appears in different slots). Needed to size the dedup layer.
- Share of non-English titles in the main feed.
- GDELT redistribution / attribution terms **[memory]**: open use with citation requested. Check before any public hosted demo.
- Events/Mentions content beyond the earlier note that old events can reappear (2 of 663 rows had a 2016 `SQLDATE`). **[verified, earlier]**

---

## 2. GKG record layout (27 tab-separated columns, no header)

Column positions confirmed against real rows; names are from the GDELT 2.1 GKG codebook **[memory]**.

| # | Name | Used by newsdock MVP? | Notes |
|---|---|---|---|
| 1 | GKGRECORDID | yes | `<slot>-<n>`; unique per record, not per article |
| 2 | DATE | fallback | When GDELT processed the record (slot time), not publish time |
| 3 | SourceCollectionIdentifier | no | 1 = web |
| 4 | SourceCommonName | yes (`domain`) | |
| 5 | DocumentIdentifier | yes (`url`) | Article URL; dedup key after normalisation |
| 6 | V1 Counts | no | |
| 7 | V2 Counts | no | |
| 8 | V1 Themes | fallback | `;`-separated codes |
| 9 | V2 Enhanced Themes | yes (`themes`) | `CODE,charOffset;…`; strip offsets, dedupe |
| 10 | V1 Locations | no | |
| 11 | V2 Locations | no (later) | `type#name#country#adm1#…#lat#lon#…` |
| 12 | V1 Persons | no | |
| 13 | V2 Persons | yes (`persons`) | `Name,offset;…` |
| 14 | V1 Organizations | no | |
| 15 | V2 Organizations | yes (`orgs`) | `Name,offset;…` |
| 16 | V2 Tone | yes | 7 numbers: tone, positive, negative, polarity, activity ref., self/group ref., word count |
| 17 | Dates | no | |
| 18 | GCAM | no | Hundreds of dictionary scores, large |
| 19 | SharingImage | no | |
| 20–22 | Related images, social image/video embeds | no | |
| 23 | Quotations | no | |
| 24 | AllNames | no | |
| 25 | Amounts | no | `value,unit,offset` |
| 26 | TranslationInfo | no | Empty in the main feed |
| 27 | Extras (XML-like) | yes | Contains `<PAGE_TITLE>`, usually `<PAGE_PRECISEPUBTIMESTAMP>`, sometimes `<PAGE_ALTURL_AMP>`, `<PAGE_LINKS>` |

**There is no article body anywhere in the record.** The MVP works from title, URL, themes, entities and tone. Body extraction means scraping third-party sites (legal and robustness cost), so it is backlog M3, as is embedding.

---

## 3. One real record (slot `20261004081500`, `GKGRECORDID 20261004081500-23`)

Picked because it has themes, persons and organisations. Long values are cut with `…`. **[verified]**

| # | Field | Value |
|---|---|---|
| 1 | GKGRECORDID | `20261004081500-23` |
| 2 | DATE | `20261004081500` |
| 3 | SourceCollection | `1` |
| 4 | SourceCommonName | `thehindubusinessline.com` |
| 5 | DocumentIdentifier | `https://www.thehindubusinessline.com/news/germany-eyes-doubling-indian-tourist-overnight-stays-by-2030-gntb-chief/article71543114.ece` |
| 6–7 | Counts | empty |
| 8 | V1Themes | `TAX_ETHNICITY;TAX_ETHNICITY_INDIAN;TOURISM;WB_825_TOURISM;WB_1921_PRIVATE_SECTOR_DEVELOPMENT;WB_346_COMPETITIVE_INDUSTRIES;WB_818_INDUSTRY_POLICY_AND_REAL_SECTO…` |
| 9 | V2EnhancedThemes | `EPU_ECONOMY,1070;EPU_ECONOMY,1257;EPU_ECONOMY,1847;EPU_ECONOMY_HISTORIC,1070;EPU_ECONOMY_HISTORIC,1257;EPU_ECONOMY_HISTORIC,1847;TAX_FNCACT_CHIEF,109;EPU_CATS_M…` |
| 10 | V1Locations | `4#Munich, Bayern, Germany#GM#GM02#48.15#11.5833#-1829149;1#India#IN#IN#20#77#IN;1#Germany#GM#GM#51.5#10.5#GM` |
| 11 | V2Locations | `4#Munich, Bayern, Germany#GM#GM02#16532#48.15#11.5833#-1829149#2520;1#Germany#GM#GM##51.5#10.5#GM#7;1#Germany#GM#GM##51.5#10.5#GM#337;…` |
| 12 | V1Persons | `forwardkeys amadeus;petra hedorfer` |
| 13 | V2Persons | `Forwardkeys Amadeus,2590;Petra Hedorfer,124` |
| 14 | V1Orgs | `german national tourist board` |
| 15 | V2Orgs | `German National Tourist Board,504` |
| 16 | V2Tone | `2.92096219931271,3.78006872852234,0.859106529209622,4.63917525773196,22.3367697594502,0.859106529209622,512` |
| 17 | Dates | empty |
| 18 | GCAM | `wc:512,c1.2:3,c1.3:1,c12.1:26,c12.10:51,c12.11:2,…` |
| 19 | SharingImage | `https://bl-i.thgim.com/public/incoming/qrfrwb/article71543130.ece/alternates/LANDSCAPE_1200/IMG_PO10_Busi_growth_2_1_8HEO8NBH.jpg` |
| 20–21 | Related images, social images | empty |
| 22 | SocialVideoEmbeds | `https://youtube.com/user/HinduBusinessLine;` |
| 23 | Quotations | empty |
| 24 | AllNames | `Petra Hedorfer,132;German National Tourist Board,543` |
| 25 | Amounts | `635,overnight stays,328;565,overnight stays by Indian,503;400,overnight stays,616;2,countries,925;3000000000,euros,1529;5,major Indian gateways,2171;510,flights…` |
| 26 | TranslationInfo | empty |
| 27 | Extras | `<PAGE_PRECISEPUBTIMESTAMP>20261004065200</PAGE_PRECISEPUBTIMESTAMP><PAGE_ALTURL_AMP>https://www.thehindubusinessline.com/news/germany-eyes-doubling-indian-touri…</PAGE_ALTURL_AMP><PAGE_TITLE>Germany eyes doubling Indian tourist overnight stays by 2030: GNTB chief</PAGE_TITLE>` |

What the processor would store for this row:

```json
{
  "url_hash": "sha256(normalized url)",
  "gkg_record_id": "20261004081500-23",
  "slot": "20261004081500",
  "url": "https://www.thehindubusinessline.com/news/germany-eyes-doubling-…/article71543114.ece",
  "title": "Germany eyes doubling Indian tourist overnight stays by 2030: GNTB chief",
  "domain": "thehindubusinessline.com",
  "published_at": "2026-10-04T06:52:00Z",
  "themes": ["EPU_ECONOMY", "EPU_ECONOMY_HISTORIC", "TAX_FNCACT_CHIEF", "..."],
  "persons": ["Forwardkeys Amadeus", "Petra Hedorfer"],
  "orgs": ["German National Tourist Board"],
  "tone": {"tone": 2.92, "positive": 3.78, "negative": 0.86, "polarity": 4.64, "word_count": 512}
}
```

---

## 4. Analysis and design consequences

1. **Title lives inside column 27**, in an XML-like tag, not in its own column. The processor must extract `<PAGE_TITLE>` and send rows without it to the dead-letter topic.
2. **Two timestamps.** Column 2 is when GDELT processed the record (here 08:15); `<PAGE_PRECISEPUBTIMESTAMP>` is when the article was published (here 06:52, 1 h 23 min earlier). The tag exists on only 65% of rows in this slot. **Proposed:** `published_at` = precise timestamp when present, else column 2. **Not yet applied:** `design.md` and `design-detail.md` still say column 2. Open TODO.
3. **Empty fields are normal.** 16% of rows have no themes, 21% no persons, 28% no orgs. Missing themes/persons/orgs must not send a row to the dead-letter topic; only a missing URL or title does.
4. **Use the V2 columns** (9, 13, 15) for themes, persons and orgs, stripping the `,offset` suffix, with V1 themes (col 8) as fallback. V1 persons/orgs are lower-cased, V2 keep original casing.
5. **Dedup keying.** Record ids are unique per record, so dedup uses a normalised URL hash. No duplicate URLs were found inside one slot, so duplicates are expected mostly across slots, but that rate is unmeasured.
6. **Volume is small** (342–527 rows per slot). Kafka is justified by learning and decoupling, not throughput. The README should say so.
7. **Finance angle for the demo agent.** About 24% of rows in the sampled slot carry an `ECON_` or finance-flavoured `WB_` theme. Themes + title + tone are the signals available; this sample row (economy-flavoured tourism news) is a good borderline case for the labelled set (AC-14).
8. **Retry window.** Observed lag of ~12–27 min fits within the 4-cycle (1 h) retry cap in the design.

## 5. Open questions from this research
- [ ] Apply the `published_at` change (precise timestamp, fallback column 2) to `design.md`, `design-detail.md` and the AC-5 fixture expectations.
- [ ] Measure the cross-slot duplicate rate over several consecutive slots.
- [ ] Measure the non-English share of titles.
- [ ] Confirm GDELT attribution terms before any public demo.
