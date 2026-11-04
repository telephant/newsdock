"""Pure functions that build the search eval fixture (M3f, ADR-0039). No I/O.

GDELT says which articles are about one event (a mention names an event and a URL).
Syndicated copies are collapsed first, an event with two or more different articles is a
cluster, articles that mention many events (roundups) are dropped from clusters, and one
seed article per cluster is the source of the query. `build_search_eval.py` wraps this
with the network and Ollama.
"""

import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from newsdock_core.contracts import CleanArticle, CleanMention
from newsdock_core.stories import story_key

Clusters = dict[int, frozenset[str]]
KINDS = ("paraphrase", "keywords")


class FixtureError(ValueError):
    """The fixture breaks one of the rules of the spec (AC-1, AC-3, AC-4)."""


def collapse(
    articles: Iterable[CleanArticle],
) -> tuple[list[CleanArticle], dict[str, str]]:
    """One article per `story_key` (lowest id) and the map id -> representative id."""
    first: dict[str, CleanArticle] = {}
    for article in sorted(articles, key=lambda a: a.url_hash):
        first.setdefault(story_key(article.title), article)
    rep_of = {a.url_hash: first[story_key(a.title)].url_hash for a in articles}
    return sorted(first.values(), key=lambda a: a.url_hash), rep_of


def derive_clusters(
    rep_of: Mapping[str, str], mentions: Iterable[CleanMention]
) -> Clusters:
    """Events mentioned by 2 or more different (collapsed) stored articles."""
    members: dict[int, set[str]] = defaultdict(set)
    for mention in mentions:
        rep = rep_of.get(mention.url_hash)
        if rep is not None:
            members[mention.event_id].add(rep)
    return {e: frozenset(m) for e, m in members.items() if len(m) >= 2}


def drop_roundups(clusters: Clusters, *, max_events: int = 3) -> Clusters:
    """Remove articles in more than `max_events` clusters, then thin and dedupe.

    Roundup pieces mention many events and blur the labels. Clusters left with fewer
    than two articles go; clusters with the same members are kept once, under the
    lowest event id.
    """
    per_article = Counter(a for members in clusters.values() for a in members)
    loose = {a for a, count in per_article.items() if count > max_events}
    kept: Clusters = {}
    seen: set[frozenset[str]] = set()
    for event_id in sorted(clusters):
        tight = frozenset(a for a in clusters[event_id] if a not in loose)
        if len(tight) >= 2 and tight not in seen:
            seen.add(tight)
            kept[event_id] = tight
    return kept


def pick_seeds(clusters: Clusters) -> dict[int, str]:
    """The seed of each cluster: its lowest article id (deterministic)."""
    return {event_id: min(members) for event_id, members in clusters.items()}


AMBIGUOUS_OVERLAP = 0.8  # share of significant words two titles have in common


def word_overlap(a: str, b: str) -> float:
    """Shared significant words (more than 3 letters) over the smaller title's count."""
    wa = {w for w in re.findall(r"[a-z0-9']+", a.casefold()) if len(w) > 3}
    wb = {w for w in re.findall(r"[a-z0-9']+", b.casefold()) if len(w) > 3}
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def query_ok(text: str, lowered_titles: Iterable[str]) -> bool:
    """AC-3: non-empty, and neither equal to nor containing (nor inside) a title."""
    wanted = text.strip().casefold()
    if not wanted:
        return False
    return not any(title in wanted or wanted in title for title in lowered_titles)


def _one_line(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return first.strip().strip("\"'`").strip().rstrip(".").strip()


def assemble(
    articles: Sequence[CleanArticle],
    mentions: Sequence[CleanMention],
    chat: Callable[[str, str], str],
    judge: Callable[[str, str], bool],
    *,
    max_clusters: int,
    distractors: int,
    rng_seed: int,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Corpus and queries from the articles and mentions of the slots.

    `chat(kind, seed_title)` writes one query for a kind (`paraphrase`, `keywords`);
    `judge(seed_title, member_title)` says whether a member is about the seed's story.
    Everything is deterministic given the inputs and `rng_seed`. Queries that break
    AC-3 are dropped, not retried.
    """
    reps, rep_of = collapse(articles)
    by_id = {a.url_hash: a for a in reps}
    clusters = drop_roundups(derive_clusters(rep_of, mentions))
    rng = random.Random(rng_seed)
    event_ids = sorted(clusters)
    if len(event_ids) > max_clusters:
        event_ids = sorted(rng.sample(event_ids, max_clusters))
    seeds = pick_seeds({e: clusters[e] for e in event_ids})
    in_clusters = {a for e in event_ids for a in clusters[e]}
    pool = sorted(set(by_id) - in_clusters)
    chosen = in_clusters | set(rng.sample(pool, min(distractors, len(pool))))
    lowered = [by_id[a].title.casefold() for a in chosen]
    queries: list[dict[str, Any]] = []
    ambiguous: set[str] = set()
    used_seeds: set[str] = set()
    used_texts: set[tuple[str, str]] = set()
    for event_id in event_ids:
        seed = seeds[event_id]
        seed_title = by_id[seed].title
        # GDELT's event links are noisy: keep a member only if the judge agrees it is
        # about the same story as the seed (ADR-0039). Rejected members stay in the
        # corpus as hard negatives, unless their title is nearly the seed's: the judge
        # often refuses near-identical headlines, so those are ambiguous and are left
        # out rather than counted as irrelevant.
        members = [seed]
        for m in sorted(clusters[event_id] - {seed}):
            if judge(seed_title, by_id[m].title):
                members.append(m)
            elif word_overlap(seed_title, by_id[m].title) >= AMBIGUOUS_OVERLAP:
                ambiguous.add(m)
        members.sort()
        if len(members) < 2 or seed in used_seeds:
            continue  # too thin, or this seed already has queries (first event wins)
        used_seeds.add(seed)
        for kind in KINDS:
            text = _one_line(chat(kind, seed_title))
            if (text.casefold(), kind) in used_texts:
                continue  # the same query for another cluster would label it twice
            if query_ok(text, lowered):
                used_texts.add((text.casefold(), kind))
                queries.append(
                    {
                        "query": text, "kind": kind, "cluster": event_id,
                        "seed": seed, "members": members,
                        "expected": [m for m in members if m != seed],
                    }
                )  # fmt: skip
    kept = {m for q in queries for m in q["members"]}
    corpus = [
        {"id": a, "title": by_id[a].title, "url": by_id[a].url, "slot": by_id[a].slot}
        for a in sorted(chosen - (ambiguous - kept))
    ]
    return corpus, queries


def check_fixture(
    corpus: Sequence[Mapping[str, Any]], queries: Sequence[Mapping[str, Any]]
) -> None:
    """Raise `FixtureError` if the fixture breaks AC-1, AC-3 or AC-4."""
    ids = [str(c["id"]) for c in corpus]
    if len(set(ids)) != len(ids):
        raise FixtureError("duplicate article ids in the corpus")
    titles = {str(c["id"]): str(c["title"]) for c in corpus}
    lowered = [t.casefold() for t in titles.values()]
    in_clusters: set[str] = set()
    for q in queries:
        if not query_ok(str(q["query"]), lowered):
            raise FixtureError(f"query is empty or a title: {q['query']!r}")
        members = [str(m) for m in q["members"]]
        expected = [str(e) for e in q["expected"]]
        seed = str(q["seed"])
        missing = [m for m in members if m not in titles]
        if missing:
            raise FixtureError(
                f"cluster {q['cluster']} has ids not in the corpus: {missing}"
            )
        if seed not in members:
            raise FixtureError(f"seed {seed} is not in its cluster {q['cluster']}")
        if len(set(expected)) != len(expected) or sorted(expected) != sorted(
            m for m in members if m != seed
        ):
            raise FixtureError(
                f"expected of cluster {q['cluster']} is not its members minus the seed"
            )
        if len({story_key(titles[m]) for m in members}) < 2:
            raise FixtureError(f"cluster {q['cluster']} has one story_key only")
        in_clusters.update(members)
    if not set(ids) - in_clusters:
        raise FixtureError("the corpus has no distractor articles")
