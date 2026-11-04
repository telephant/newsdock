"""TC-2, TC-3, TC-4, TC-5 (builder half): the pure functions that build the search eval.

Articles are copies of one real fixture row with another id, title and URL; mentions are
hand-made. No network, no Ollama (the builder's chat call is a separate wrapper).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import search_eval_build as build
from newsdock_core.contracts import CleanArticle, CleanMention
from newsdock_core.gkg import parse_row

FIXTURES = Path(__file__).resolve().parents[3] / "packages/core/tests/fixtures"
NOW = datetime(2026, 11, 4, 8, tzinfo=UTC)


def _template() -> CleanArticle:
    line = (FIXTURES / "gkg_sample.tsv").read_text().splitlines()[0]
    parsed = parse_row(slot="20261104080000", row_no=0, line=line)
    assert isinstance(parsed, CleanArticle)
    return parsed


def art(key: str, title: str) -> CleanArticle:
    return _template().model_copy(
        update={"url_hash": key, "title": title, "url": f"https://{key}.example/x"}
    )


def men(event_id: int, key: str) -> CleanMention:
    return CleanMention(
        event_id=event_id, url=f"https://{key}.example/x", url_hash=key,
        source_name=None, mention_time=NOW, confidence=None,
    )  # fmt: skip


# --- TC-3: copies of one headline are one article ---------------------------------
def test_collapse_keeps_the_first_article_per_story_key() -> None:
    reps, rep_of = build.collapse(
        [art("b", "Storm hits coast"), art("a", "Storm hits coast"), art("c", "Other")]
    )
    assert sorted(a.url_hash for a in reps) == ["a", "c"]  # first by id
    assert rep_of == {"a": "a", "b": "a", "c": "c"}


def test_an_event_mentioned_only_by_copies_makes_no_cluster() -> None:
    articles = [art("a", "Storm hits coast"), art("b", "Storm hits coast")]
    _, rep_of = build.collapse(articles)
    assert build.derive_clusters(rep_of, [men(1, "a"), men(1, "b")]) == {}


# --- TC-2: clusters are exactly the articles that mention one event ---------------
def test_clusters_are_exactly_the_articles_of_one_event() -> None:
    articles = [art("a", "Alpha one"), art("b", "Beta two"), art("c", "Gamma three"),
                art("d", "Delta four")]  # fmt: skip
    _, rep_of = build.collapse(articles)
    mentions = [men(1, "a"), men(1, "b"), men(2, "b"), men(2, "c"), men(3, "d"),
                men(9, "unknown")]  # fmt: skip
    clusters = build.derive_clusters(rep_of, mentions)
    assert clusters == {1: frozenset({"a", "b"}), 2: frozenset({"b", "c"})}
    # event 3 has one article, event 9 none of ours; "d" is in no cluster
    assert all("d" not in members for members in clusters.values())


def test_a_repeated_mention_does_not_double_count() -> None:
    _, rep_of = build.collapse([art("a", "Alpha one"), art("b", "Beta two")])
    clusters = build.derive_clusters(rep_of, [men(1, "a"), men(1, "a"), men(1, "b")])
    assert clusters == {1: frozenset({"a", "b"})}


def test_drop_roundups_removes_articles_in_many_events_and_duplicate_sets() -> None:
    clusters = {
        1: frozenset({"a", "r"}), 2: frozenset({"b", "r"}), 3: frozenset({"c", "r"}),
        4: frozenset({"d", "r"}), 5: frozenset({"x", "y"}), 6: frozenset({"x", "y"}),
    }  # fmt: skip
    kept = build.drop_roundups(clusters, max_events=3)
    # "r" is in 4 events: it is dropped, leaving one-article clusters that disappear;
    # events 5 and 6 are the same member set: kept once, under the lowest event id
    assert kept == {5: frozenset({"x", "y"})}


def test_pick_seeds_takes_the_lowest_id_of_each_cluster() -> None:
    seeds = build.pick_seeds({7: frozenset({"c", "a", "b"}), 8: frozenset({"z", "y"})})
    assert seeds == {7: "a", 8: "y"}


# --- TC-1 rules, TC-4, TC-5: the fixture checker ----------------------------------
def corpus() -> list[dict[str, str]]:
    titles = {
        "a": "Voters in Ohio elect governor", "b": "Ohio picks new governor",
        "c": "Wildfire spreads in Oregon", "d": "Central bank holds rates",
    }  # fmt: skip
    return [{"id": k, "title": t, "url": f"https://{k}.example", "slot": "s"}
            for k, t in titles.items()]  # fmt: skip


def query(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "query": "who won the Ohio statehouse race", "kind": "paraphrase",
        "cluster": 1, "seed": "a", "members": ["a", "b"], "expected": ["b"],
    }  # fmt: skip
    base.update(changes)
    return base


def test_a_valid_fixture_passes() -> None:
    build.check_fixture(corpus(), [query()])  # no exception


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(build.FixtureError, match="duplicate"):
        build.check_fixture(corpus() + [corpus()[0]], [query()])


def test_a_cluster_of_one_story_is_rejected() -> None:
    same = corpus()
    same[1] = {**same[1], "title": "Voters in Ohio elect governor"}
    with pytest.raises(build.FixtureError, match="story_key"):
        build.check_fixture(same, [query()])


def test_a_corpus_without_distractors_is_rejected() -> None:
    only_cluster = [c for c in corpus() if c["id"] in {"a", "b"}]
    with pytest.raises(build.FixtureError, match="distractor"):
        build.check_fixture(only_cluster, [query()])


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "Voters in Ohio elect governor", "voters in ohio elect governor now",
     "Ohio picks new governor"],
)  # fmt: skip
def test_a_query_that_is_empty_or_a_title_is_rejected(bad: str) -> None:
    with pytest.raises(build.FixtureError, match="query"):
        build.check_fixture(corpus(), [query(query=bad)])


@pytest.mark.parametrize(
    "changes",
    [
        {"expected": ["missing"]},  # not in the corpus
        {"expected": ["c"]},  # in the corpus but not in the cluster
        {"expected": ["a"]},  # the seed
        {"members": ["a", "b"], "seed": "c"},  # seed outside its cluster
        {"expected": ["b", "b"]},  # duplicates
    ],
)
def test_expected_ids_must_be_the_cluster_without_the_seed(
    changes: dict[str, object],
) -> None:
    with pytest.raises(build.FixtureError):
        build.check_fixture(corpus(), [query(**changes)])


# --- assemble: articles and mentions of the slots -> corpus and queries (stub chat) --
def _world() -> tuple[list[CleanArticle], list[CleanMention]]:
    articles = [
        art("a1", "Ohio voters pick a new governor"),
        art("a2", "Statehouse race in Ohio decided"),
        art("b1", "Wildfire spreads across Oregon hills"),
        art("b2", "Oregon blaze forces evacuations"),
        art("d1", "Central bank holds interest rates"),
        art("d2", "Cat show draws record crowd"),
        art("d3", "New phone launches next week"),
    ]
    mentions = [men(1, "a1"), men(1, "a2"), men(2, "b1"), men(2, "b2")]
    return articles, mentions


def stub_chat(kind: str, title: str) -> str:
    answers = {"paraphrase": "who is running the state now", "keywords": "state race"}
    return f"{answers[kind]} {title.split()[0].casefold()}"  # differs per seed


def always_yes(seed_title: str, member_title: str) -> bool:
    return True


def test_assemble_builds_a_valid_deterministic_fixture() -> None:
    articles, mentions = _world()
    corpus1, queries1 = build.assemble(
        articles, mentions, stub_chat, always_yes,
        max_clusters=10, distractors=2, rng_seed=0,
    )  # fmt: skip
    corpus2, queries2 = build.assemble(
        articles, mentions, stub_chat, always_yes,
        max_clusters=10, distractors=2, rng_seed=0,
    )  # fmt: skip
    assert (corpus1, queries1) == (corpus2, queries2)
    build.check_fixture(corpus1, queries1)  # valid by the spec's rules
    assert {q["kind"] for q in queries1} == {"paraphrase", "keywords"}
    assert len(queries1) == 4  # two clusters, two kinds
    ids = {c["id"] for c in corpus1}
    assert {"a1", "a2", "b1", "b2"} <= ids and len(ids - {"a1", "a2", "b1", "b2"}) == 2
    assert {q["cluster"] for q in queries1} == {1, 2}
    for q in queries1:  # seed is the lowest id; expected is the rest of the cluster
        assert q["seed"] == min(q["members"])
        assert q["expected"] == [m for m in q["members"] if m != q["seed"]]


def test_assemble_drops_queries_that_copy_a_title_and_caps_clusters() -> None:
    articles, mentions = _world()

    def copying(kind: str, title: str) -> str:
        return title if kind == "keywords" else "who is running the state now"

    _, queries = build.assemble(
        articles, mentions, copying, always_yes,
        max_clusters=1, distractors=1, rng_seed=0,
    )  # fmt: skip
    assert [q["kind"] for q in queries] == ["paraphrase"]  # the copy was dropped
    assert len({q["cluster"] for q in queries}) == 1  # capped at one cluster


# --- TC-17 (AC-13): members are verified against the seed by a judge -------------
def _judged_world() -> tuple[list[CleanArticle], list[CleanMention]]:
    articles = [
        art("a1", "Ohio voters pick a new governor"),
        art("a2", "Statehouse race in Ohio decided"),
        art("a3", "Cat show draws record crowd"),  # linked by GDELT, not the same story
        art("d1", "Central bank holds interest rates"),
        art("d2", "New phone launches next week"),
    ]
    return articles, [men(1, "a1"), men(1, "a2"), men(1, "a3")]


def test_a_member_the_judge_rejects_leaves_expected_but_stays_in_the_corpus() -> None:
    articles, mentions = _judged_world()

    def judge(seed_title: str, member_title: str) -> bool:
        return "Cat" not in member_title

    corpus, queries = build.assemble(
        articles, mentions, stub_chat, judge, max_clusters=5, distractors=1, rng_seed=0
    )
    build.check_fixture(corpus, queries)
    assert {q["seed"] for q in queries} == {"a1"}
    assert all(
        q["members"] == ["a1", "a2"] and q["expected"] == ["a2"] for q in queries
    )
    assert "a3" in {c["id"] for c in corpus}  # a hard negative, not dropped


def test_a_rejected_near_duplicate_is_left_out_of_the_corpus_not_made_a_negative() -> (
    None
):
    articles = [
        art("a1", "Tube producing plant established in western Afghanistan"),
        art("a2", "Afghan officials open a new plant for steel tubes"),
        art("a3", "Tube producing plant established in western Afghanistan-Xinhua"),
        art("a4", "Cat show draws record crowd"),
        art("d1", "Central bank holds interest rates"),
    ]
    mentions = [men(1, "a1"), men(1, "a2"), men(1, "a3"), men(1, "a4")]

    def judge(seed_title: str, member_title: str) -> bool:
        return "steel" in member_title  # wrongly says no to the near-duplicate a3

    corpus, queries = build.assemble(
        articles, mentions, stub_chat, judge, max_clusters=5, distractors=1, rng_seed=0
    )
    ids = {c["id"] for c in corpus}
    assert all(q["members"] == ["a1", "a2"] for q in queries)
    assert "a3" not in ids  # ambiguous: almost the seed's headline, judged "no"
    assert "a4" in ids  # clearly unrelated: a true hard negative


def test_two_clusters_with_the_same_seed_make_queries_once() -> None:
    articles = [
        art("a1", "Ohio voters pick a new governor"),
        art("a2", "Statehouse race in Ohio decided"),
        art("a3", "Ohio governor candidate gives victory speech"),
        art("d1", "Central bank holds interest rates"),
    ]
    mentions = [men(1, "a1"), men(1, "a2"), men(2, "a1"), men(2, "a3")]

    corpus, queries = build.assemble(
        articles, mentions, stub_chat, always_yes,
        max_clusters=5, distractors=1, rng_seed=0,
    )  # fmt: skip
    build.check_fixture(corpus, queries)
    assert [q["cluster"] for q in queries] == [1, 1]  # the first cluster only
    assert len({(q["query"], q["kind"]) for q in queries}) == len(queries)


def test_a_query_text_already_used_for_another_cluster_is_not_repeated() -> None:
    articles, mentions = _world()

    def same_for_all(kind: str, title: str) -> str:
        return {"paraphrase": "who runs the state", "keywords": "state race"}[kind]

    _, queries = build.assemble(
        articles, mentions, same_for_all, always_yes,
        max_clusters=5, distractors=1, rng_seed=0,
    )  # fmt: skip
    texts = [(q["query"], q["kind"]) for q in queries]
    assert len(texts) == len(set(texts)) == 2  # one cluster keeps both kinds, once


def test_a_cluster_with_no_verified_member_makes_no_queries() -> None:
    articles, mentions = _judged_world()

    def judge(seed_title: str, member_title: str) -> bool:
        return False

    corpus, queries = build.assemble(
        articles, mentions, stub_chat, judge, max_clusters=5, distractors=1, rng_seed=0
    )
    assert queries == []
    assert {"a1", "a2", "a3"} <= {
        c["id"] for c in corpus
    }  # candidates stay as negatives


# --- hybrid-eval-set (M3g): names, grading, the hard queries -------------------------
@pytest.mark.parametrize(
    ("title", "names"),
    [
        # names, a sentence-initial word and a trailing clause cut by the limit
        ("Democrat Amy Acton wins race for Ohio governor, AP projects",
         ["Amy", "Acton", "Ohio"]),
        # outlet suffix after " | " is cut; "Wins" is a title-case non-name
        ("Abdul El-Sayed Wins Michigan Senate Race | NewsRadio 910 WLTP",
         ["El-Sayed", "Michigan", "Senate"]),
        # HTML entity, acronyms kept, sentence-initial words after a colon skipped
        ("REFORMS: Oil output has grown by 600,000bpd since PIA &#x2014; NNPC",
         ["PIA", "NNPC"]),
        # possessive loses its 's
        ("Republican Byron Donalds is elected Florida's first Black governor",
         ["Byron", "Donalds", "Florida"]),
        # a word after a full stop starts a sentence: skipped
        ("Democrats just took back control of Congress. What's next?", ["Congress"]),
        # filler acronym AP is not a name
        ("Hochul elected to second full-term as NY governor, AP projects", ["NY"]),
        # no names at all
        ("oil prices fall again after the storm", []),
        # distinct, in title order, at most 3
        ("Paris Berlin Rome Madrid Paris", ["Berlin", "Rome", "Madrid"]),
    ],
)  # fmt: skip
def test_names_are_cut_cleanly_from_a_title(
    title: str, names: list[str]
) -> None:  # TC-1
    assert build.extract_names(title) == names


def test_the_name_limit_can_be_lowered() -> None:
    assert build.extract_names("Said Berlin Rome Madrid", limit=2) == ["Berlin", "Rome"]


def test_members_are_graded_by_their_word_overlap_with_the_seed() -> None:  # TC-3
    titles = {
        "seed": "Democrat Amy Acton wins Ohio governor race",
        "same": "Amy Acton wins race for Ohio governor",
        "other": "Voters pick new leader in Columbus runoff",
    }
    graded, ignored = build.grade_members("seed", ["same", "other"], titles)
    assert graded == ["other"] and ignored == ["same"]
    assert build.grade_members("seed", ["same"], titles) == ([], ["same"])


def _frozen() -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    titles = {
        "a1": "Democrat Amy Acton wins Ohio governor race",
        "a2": "Amy Acton wins race for Ohio governor",
        "a3": "Voters pick new leader in Columbus runoff",
        "b1": "Wildfire spreads across Oregon hills",
        "b2": "Oregon wildfire spreads across hills quickly",
        "d1": "Central bank holds interest rates",
    }
    corpus = [{"id": k, "title": t, "url": f"https://{k}", "slot": "s"}
              for k, t in titles.items()]  # fmt: skip
    queries: list[dict[str, object]] = [
        {"query": "who runs Columbus now", "kind": "paraphrase", "cluster": 1,
         "seed": "a1", "members": ["a1", "a2", "a3"], "expected": ["a2", "a3"]},
        {"query": "state blaze news", "kind": "paraphrase", "cluster": 2,
         "seed": "b1", "members": ["b1", "b2"], "expected": ["b2"]},
    ]  # fmt: skip
    return corpus, queries


def test_hard_queries_have_entity_and_low_overlap_rows() -> None:  # TC-3, TC-4
    corpus, queries = _frozen()
    rows = build.build_hard_queries(corpus, queries)
    by_kind = {(r["kind"], r["cluster"]): r for r in rows}
    entity = by_kind[("entity", 1)]
    assert entity["query"] == "Amy Acton Ohio"  # names of the seed title
    assert entity["expected"] == ["a2", "a3"] and entity["ignore"] == []
    low = by_kind[("lowoverlap", 1)]
    assert low["query"] == "who runs Columbus now"  # the cluster's paraphrase text
    assert low["expected"] == ["a3"] and low["ignore"] == ["a2"]
    # cluster 2: one name only ("Oregon"), and its member is a near rewording
    assert ("entity", 2) not in by_kind and ("lowoverlap", 2) not in by_kind
    build.check_hard_fixture(corpus, rows)  # valid by the spec's rules


def test_a_repeated_entity_text_is_kept_once() -> None:
    corpus, queries = _frozen()
    corpus += [
        {"id": "c1", "title": "Reports say Amy Acton visits Ohio schools", "url": "u",
         "slot": "s"},
        {"id": "c2", "title": "Plan for Columbus transit unveiled", "url": "u",
         "slot": "s"},
    ]  # fmt: skip
    queries.append(
        {"query": "transit plan news", "kind": "paraphrase", "cluster": 3,
         "seed": "c1", "members": ["c1", "c2"], "expected": ["c2"]}
    )  # fmt: skip
    rows = build.build_hard_queries(corpus, queries)
    texts = [(r["kind"], r["query"]) for r in rows]
    assert len(texts) == len(set(texts))  # "Amy Acton Ohio" from cluster 1 only
    assert [r["cluster"] for r in rows if r["kind"] == "entity"] == [1]


def _hard_rows() -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    corpus, queries = _frozen()
    return corpus, build.build_hard_queries(corpus, queries)


@pytest.mark.parametrize(
    "changes",
    [
        {"expected": ["nope"]},  # unknown id
        {"ignore": ["a3"]},  # overlaps expected (lowoverlap row, a3 is graded)
        {"expected": ["a3", "d1"]},  # a member outside the cluster
        {"query": ""},  # empty text
        {"query": "Amy Acton wins Ohio governor race"},  # equals a title
    ],
)
def test_check_hard_fixture_rejects_broken_rows(changes: dict[str, object]) -> None:
    corpus, rows = _hard_rows()
    low = next(r for r in rows if r["kind"] == "lowoverlap")
    broken = [{**low, **changes}]
    with pytest.raises(build.FixtureError):
        build.check_hard_fixture(corpus, broken)


def test_check_hard_fixture_rejects_a_repeated_text_within_a_kind() -> None:
    corpus, rows = _hard_rows()
    entity = next(r for r in rows if r["kind"] == "entity")
    with pytest.raises(build.FixtureError, match="repeated"):
        build.check_hard_fixture(corpus, [entity, {**entity, "cluster": 9}])


def test_check_hard_fixture_needs_two_names_in_an_entity_query() -> None:
    corpus, rows = _hard_rows()
    entity = next(r for r in rows if r["kind"] == "entity")
    with pytest.raises(build.FixtureError, match="names"):
        build.check_hard_fixture(corpus, [{**entity, "query": "Ohio"}])
