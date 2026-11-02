# ADR-0031: Story-first digest: lexical grouping behind a port, score by coverage and tone

Status: **Accepted 2026-11-02** (spec `digest-top-stories`, D-1, D-3, D-4, D-5; confirmed by the user during `/spec-design`)

## Context
The first digest grouped by GDELT theme codes (spec `what-happen`). Real output showed themes mixing unrelated stories, and the same event arriving as several rows (51 and 61 sources for one senator's stroke). The user chose a story-first digest, ranked by coverage and tone, with headlines merged by a lexical title match in the agent (no embeddings: the platform will provide clustering later) and fixed plain-language sections. The agent is an independent server (ADR-0029): it can only use what MCP returns.

## Options
**Grouping:** (a) lexical title match in the agent; (b) embeddings in the agent through Ollama; (c) wait for platform clustering; (d) the model judges pairs.
**Matching guard against chaining:** (a) compare to the group's seed only; (b) single-link union-find.
**Template false merges:** (a) a same-domain guard (the platform's own `can_join` idea); (b) a document-frequency cap; (c) a numeric veto.
**Section label:** (a) first matching prefix; (b) vote over the group's theme hits; (c) model labels.

## Decision
- **Lexical grouping in the agent (a)**, behind a `StoryGrouper` port so platform clustering can replace it. Rule: significant-word sets (stop-words dropped, plurals folded, long words truncated to 6), overlap ≥ 0.75 or Jaccard ≥ 0.5 with at least 3 shared words, within 48 hours of the group's seed.
- **Seed-only matching (a)**: single-link chaining would let one loose pair snowball.
- **Same-domain guard (a)**: an outlet does not publish the same story twice, so a second page of the same domain never joins a group. Prototype on 710 real headlines: it removed the one observed false-merge class (nine sports-ranking headlines on template words) and no real merge. The document-frequency cap was tried and rejected (it broke every real group: event words are frequent because many rows report the event); the numeric veto never fired (single digits are dropped as tokens).
- **Section by vote (b)**: theme codes are noisy on real data, so the label with the most hits across a group's articles wins; none means "Other".
- **Score = sources × (1 + tone_neg / 10)** with a coverage-only fallback.

## Consequences
+ Deterministic, fast, no model or embeddings; the same input gives the same grouping, so it is testable with real pairs.
+ A later replacement is one class (the port), not a rewrite.
− Crude: paraphrases with different words stay separate (a second Murphy group of 12 sources appeared in the prototype) and an event may appear twice.
− Thresholds are tuned on one day of data; they are settings and re-measured at verify.
− The same-domain guard can split a real group if an outlet runs two pages on one story; accepted.
− Sections are only as good as the theme codes; "Other" will hold some stories.
− The hourly view sees `source_count` early (spec risk 1); a rolling window is the first backlog item.
