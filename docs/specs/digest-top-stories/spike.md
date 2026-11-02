# digest-top-stories — Spike (T-01)

Run 2026-11-02 on the dev database, read-only, with throwaway scripts outside the repo (run with `python -I`). No production code changed. Everything below was measured this session, so it is **[verified]** unless marked otherwise.

**Verdict: the mechanics hold; ranking quality is moderate and needs one decision (below).**

## (a) Three real hourly windows (07:00, 08:00, 09:00 UTC, all articles, `source_count` as the agent would see it five minutes after the hour)

| | 07:00 | 08:00 | 09:00 |
|---|---|---|---|
| Articles read | 1 702 | 1 613 | 1 729 |
| Groups after merging | 1 648 | 1 575 | 1 695 |
| Articles with 2+ sources (copies / distinct domains) | 107 / 96 | 57 / 52 | 75 / 60 |
| Groups listed (2+ sources) | 137 | 85 | 92 |
| Sections filled / groups in "Other" | 7 / 42 of 132 | 7 / 18 of 80 | 7 / 29 of 87 |

Every hour fills a Top 5 and all sections, so a thin block is not the problem. The tail is thin in the quiet hour: at 08:00 the 3rd to 5th stories had only 7, 6 and 5 sources.

## (b) Cost

The seed-based grouper with a token index took **0.02 s** for about 1 700 titles (40 000 to 49 000 comparisons). No performance concern.

## (c) Merge quality

On 710 multi-source headlines of one day (earlier prototype) and the three hours: rewordings of one event merge (Murphy 9 rows / 152 sources, Stevens, the Florida jet crash, the UN mission ending, the Alaska ruling), unrelated pairs stay apart, and the same-domain guard removes the sports-template false merge. Known miss: a few rewordings stay separate. 4 of 4 decided pairs correct under the overlap rule; the full labelled set is committed as `story_pairs.json` (14 pairs, 9 same, plus 4 same-domain "Field Level Media Top 25" template headlines).

## (d) Fixtures committed

`agents/whathappen/tests/fixtures/story_window.json`: the 08:00 hour (1 613 rows in the `list_new_articles` shape, `source_count` as seen early, `tone_neg`, themes without the generic families `TAX_ WB_ EPU_ CRISISLEX_ USPEC_ UNGP_ GENERAL_ MEDIA_ SOC_ LEADER AFFECT`, which nothing here reads; 715 KB). `story_pairs.json`: 14 labelled pairs and the template rows. Titles and URLs are public news, like the existing `digest_window.json`.

## (e) What the data says about the ranking (this is the finding)

**Coverage mostly measures syndication reach, not importance.** In the three hours the Top 5 by `sources × (1 + tone_neg/10)` contained clearly important items (the Florida jet crash, a UN peacekeeping mission ending, the UK immigration debate, the Binance hack) next to syndicated or soft items: "Props From 'Batman Returns' Up For Auction | News Talk 550 KFYI" (29 sources), "New fabrication hall opens at Harland and Wolff" (30 sources, tone 0.2), "Janelle Monáe debuts fish-inspired look", "Walkers recalls crisps". About 1 to 2 of every 5 top slots were soft.

Why: radio-station networks (`iheart.com` pages per station) and local-newspaper chains republish one headline on dozens of sites, and the platform counts each copy as a source. Negative tone barely changes the order, because widely covered stories are mildly negative (median 3.6) and the soft items are not more positive than the hard ones.

Things tried on the same three hours:

| Variant | Result |
|---|---|
| Count distinct domains instead of copies | Removes the iHeart station duplicates (the Batman-props item leaves hour 07's Top 5 and the jet crash enters); does **not** remove a real newspaper chain (the hall opening has 30 distinct domains). Needs one `get_article` call per candidate (about 30 a cycle) or a future platform field |
| Boost by the number of distinct headline variants in a group (independent rewording) | Lifts the jet crash to #1 in hour 07, but also lifts a press release republished with small title changes and the sports-template group. Mixed |
| Document-frequency cap on title words | Breaks every real group (event words are frequent because many rows report the event). Rejected |
| Strip a trailing " \| outlet" from titles | 6.9% of titles and 13.8% of 2+ source rows carry one (10 of the 40 best-covered); stripping makes display cleaner and matching better. Cheap and safe |

**Late growth (risk 1) is smaller than feared.** For each hour, all five stories that are in the top 5 by today's (final) counts were already in the early top 10. The order inside the block changes (the jet crash had 4 sources in hour 08 and 61 later) but the right stories are present.

**Sections are a weak signal.** With the vote and one required hit, roughly 60% of sectioned stories look right in the sample read ("Juan Atkins, techno co-creator, has died" under Conflict & Security; an amateur-historian piece under Disasters). Requiring two hits moves "Other" from 41 to 72 of 121 groups and fixes some misfiles but not all. Neither is clearly better; a `section_min_hits` setting (default 1) lets the owner choose.

## Recommendation

Keep the approved design (score by copies and tone, hourly window, vote sections) and add two cheap, safe changes:

1. Strip a trailing " | outlet" segment from titles before grouping and display.
2. Add a `section_min_hits` setting (default 1).

Record **`domain_count` in the platform's article summary** as the proper fix for syndication inflation (a backlog item for the platform, not an agent workaround), and keep distinct-domain counting via `get_article` as the optional fallback if the Top block proves too soft in use.
