"""Support code for the search eval (M3a, extended by M3f `harder-search-eval`).

Pure parts (metrics, leave-one-out, noise, paired bootstrap) and the parts that need a
Postgres and an embedder (load a dataset, run the four methods, sweep the settings).
The datasets are `easy` (the original 40 hand-written titles) and `events` (real titles,
relevance from GDELT events confirmed by a local model, frozen by
`make eval-search-build`). See ADR-0039.
"""

import json
import random
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

import httpx
from newsdock_api.adapters.query_embedder import OllamaQueryEmbedder
from newsdock_api.adapters.repo import SqlArticleRepo
from newsdock_api.adapters.semantic_repo import SqlSemanticRepo
from newsdock_api.config import Settings
from newsdock_api.domain.semantic import QueryEmbedder, SearchFilters, SemanticService
from newsdock_db.testing import article
from newsdock_embedding import document_text, embed
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

HERE = Path(__file__).parent
FIXTURES = Path(__file__).resolve().parents[4] / "packages/core/tests/fixtures"
K = 5
EMBED_BATCH = 64  # titles per Ollama request while loading a corpus
MODEL = "nomic-embed-text"
METHODS = ("keyword", "fulltext", "vector", "hybrid")
LABELS = {
    "keyword": "keyword (search_articles substring)",
    "fulltext": "fulltext (hybrid's keyword leg)",
    "vector": "vector",
    "hybrid": "hybrid",
}
PREFIXES = {True: ("search_document: ", "search_query: "), False: ("", "")}
GRID_RRF_K = (10, 30, 60, 100)
GRID_CANDIDATES = (20, 50, 100)


# --- metrics --------------------------------------------------------------------------
def recall_at_k(expected: Sequence[str], got: Sequence[str], k: int = K) -> float:
    """Share of the expected ids found among the first k results."""
    wanted = set(expected)
    if not wanted:
        raise ValueError("a query needs at least one expected article")
    return len(wanted & set(got[:k])) / len(wanted)


def reciprocal_rank(expected: Sequence[str], got: Sequence[str]) -> float:
    """1 / rank of the first expected id in the results; 0 when none is there."""
    wanted = set(expected)
    for rank, article_id in enumerate(got, start=1):
        if article_id in wanted:
            return 1.0 / rank
    return 0.0


@dataclass
class QueryRun:
    """One query: its kind, the relevant ids and each method's ranked ids."""

    kind: str
    expected: list[str]
    found: dict[str, list[str]] = field(default_factory=dict)


def without(ids: Sequence[str], drop: Collection[str], *, k: int = K) -> list[str]:
    """Drop the seed and the ignored members, then keep the first k."""
    return [i for i in ids if i not in drop][:k]


def without_seed(ids: Sequence[str], seed: str | None, *, k: int = K) -> list[str]:
    """Leave-one-out: drop the query's seed article, then keep the first k."""
    return without(ids, set() if seed is None else {seed}, k=k)


def metrics(runs: Sequence[QueryRun], method: str) -> tuple[float, float]:
    """Mean recall@5 and MRR of one method over the runs."""
    return (
        mean(recall_at_k(r.expected, r.found[method]) for r in runs),
        mean(reciprocal_rank(r.expected, r.found[method]) for r in runs),
    )


def metrics_by_kind(
    runs: Sequence[QueryRun], method: str
) -> dict[str, tuple[float, float]]:
    kinds = sorted({r.kind for r in runs})
    return {k: metrics([r for r in runs if r.kind == k], method) for k in kinds}


@dataclass(frozen=True)
class Noise:
    """Relevant hits a leg had in its top 5 that the fused list lost (F-6)."""

    relevant_vector_hits: int
    dropped_by_hybrid_vs_vector: int
    relevant_fulltext_hits: int
    dropped_by_hybrid_vs_fulltext: int


def noise(runs: Sequence[QueryRun]) -> Noise:
    v_hits = v_dropped = f_hits = f_dropped = 0
    for run in runs:
        wanted = set(run.expected)
        hybrid = set(run.found["hybrid"][:K])
        vector = set(run.found["vector"][:K]) & wanted
        fulltext = set(run.found["fulltext"][:K]) & wanted
        v_hits += len(vector)
        v_dropped += len(vector - hybrid)
        f_hits += len(fulltext)
        f_dropped += len(fulltext - hybrid)
    return Noise(v_hits, v_dropped, f_hits, f_dropped)


def paired_bootstrap(
    a: Sequence[float], b: Sequence[float], *, n: int = 1000, seed: int = 0
) -> tuple[float, float]:
    """95% interval of mean(a - b) over queries, resampling queries with replacement."""
    diffs = [x - y for x, y in zip(a, b, strict=True)]
    rng = random.Random(seed)
    size = len(diffs)
    means = sorted(
        mean(diffs[rng.randrange(size)] for _ in range(size)) for _ in range(n)
    )
    return means[int(0.025 * n)], means[min(n - 1, int(0.975 * n))]


def clear_win(
    candidate: Sequence[QueryRun],
    baseline: Sequence[QueryRun],
    method: str,
    *,
    n: int = 1000,
    seed: int = 0,
) -> bool:
    """ADR-0039: the MRR interval excludes 0 on the plus side, recall@5 is not lower
    and no kind of query is lower in either number."""

    def mrr(runs: Sequence[QueryRun]) -> list[float]:
        return [reciprocal_rank(r.expected, r.found[method]) for r in runs]

    low, _ = paired_bootstrap(mrr(candidate), mrr(baseline), n=n, seed=seed)
    if low <= 0:
        return False
    if metrics(candidate, method)[0] < metrics(baseline, method)[0]:
        return False
    cand_kinds = metrics_by_kind(candidate, method)
    base_kinds = metrics_by_kind(baseline, method)
    return all(
        cand_kinds[k][0] >= base_kinds[k][0] and cand_kinds[k][1] >= base_kinds[k][1]
        for k in base_kinds
    )


# --- datasets -------------------------------------------------------------------------
@dataclass(frozen=True)
class Dataset:
    name: str
    corpus: list[dict[str, Any]]
    queries: list[dict[str, Any]]  # query, kind, expected, seed (None for `easy`)


def _json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_dataset(name: str) -> Dataset:
    """`easy`, `events` (M3f) or `events-hard` (M3g: same corpus, entity and
    low-overlap queries with ignored members). Every row has `seed` and `ignore`."""
    if name == "easy":
        queries = [
            {**q, "seed": None, "ignore": []} for q in _json(HERE / "queries.json")
        ]
        return Dataset("easy", _json(HERE / "corpus.json"), queries)
    corpus = _json(FIXTURES / "search_eval_corpus.json")
    if name == "events":
        frozen = _json(FIXTURES / "search_eval_queries.json")["queries"]
        return Dataset("events", corpus, [{**q, "ignore": []} for q in frozen])
    if name == "events-hard":
        hard = _json(FIXTURES / "search_eval_hard_queries.json")["queries"]
        return Dataset("events-hard", corpus, hard)
    raise ValueError(f"unknown dataset {name!r} (easy, events, events-hard)")


# --- running (needs Postgres and an embedder) ---------------------------------------
class CachingEmbedder:
    """Embeds each query text once, so a sweep does not repeat the model call."""

    def __init__(self, inner: QueryEmbedder) -> None:
        self._inner = inner
        self._cache: dict[str, list[float]] = {}

    def embed_query(self, query: str) -> list[float]:
        if query not in self._cache:
            self._cache[query] = self._inner.embed_query(query)
        return self._cache[query]


def load_corpus(
    engine: Engine,
    dataset: Dataset,
    *,
    doc_prefix: str,
    client: httpx.Client | None,
    url: str,
) -> None:
    """Embed the dataset's titles and replace the articles table with them."""
    texts = [document_text(c["title"], doc_prefix) for c in dataset.corpus]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):  # one huge request crashes Ollama
        vectors += embed(
            texts[start : start + EMBED_BATCH],
            model=MODEL, url=url, timeout=120.0, client=client,
        )  # fmt: skip
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE articles CASCADE"))
    with Session(engine) as session:
        session.add_all(
            article(c["id"], c["title"], vec=v, model=MODEL)
            for c, v in zip(dataset.corpus, vectors, strict=True)
        )
        session.commit()


def make_embedder(
    *, query_prefix: str, client: httpx.Client | None, url: str
) -> CachingEmbedder:
    return CachingEmbedder(
        OllamaQueryEmbedder(
            url=url,
            model=MODEL,
            dimension=768,
            prefix=query_prefix,
            timeout=120.0,
            client=client,
        )  # fmt: skip
    )


def run_queries(
    engine: Engine,
    dataset: Dataset,
    embedder: QueryEmbedder,
    *,
    rrf_k: int,
    candidates: int,
    methods: Sequence[str] = METHODS,
) -> list[QueryRun]:
    """Run every query through the chosen methods, seed removed, first K kept."""
    settings = Settings()
    repo = SqlSemanticRepo(engine, ef_search=settings.semantic_ef_search)
    service = SemanticService(
        repo, embedder, model=MODEL, candidates=candidates, rrf_k=rrf_k,
        max_query_length=settings.semantic_query_max_length,
        default_limit=K + 1, max_limit=100,
    )  # fmt: skip
    plain = SqlArticleRepo(engine)
    runs: list[QueryRun] = []
    for q in dataset.queries:
        query = q["query"]
        drop = set(q["ignore"]) | ({q["seed"]} if q["seed"] else set())
        fetch = K + len(drop)  # room for what is dropped, so K results remain
        raw: dict[str, list[str]] = {}
        if "keyword" in methods:
            raw["keyword"] = [
                a.article_id
                for a in plain.search(
                    time_from=None,
                    time_to=None,
                    theme=None,
                    domain=None,
                    text=query,
                    limit=fetch,
                )  # fmt: skip
            ]
        if "fulltext" in methods:
            raw["fulltext"] = [
                h.id
                for h in repo.keyword_leg(
                    query=query, filters=SearchFilters(), limit=fetch
                )
            ]
        for mode in ("vector", "hybrid"):
            if mode in methods:
                hits = service.search(query, mode=mode, limit=fetch).articles
                raw[mode] = [a.article_id for a in hits]
        runs.append(
            QueryRun(
                q["kind"],
                list(q["expected"]),
                {m: without(ids, drop) for m, ids in raw.items()},
            )  # fmt: skip
        )
    return runs


# --- reporting and the sweep --------------------------------------------------------
def print_report(
    label: str,
    dataset: Dataset,
    runs: Sequence[QueryRun],
    *,
    rrf_k: int,
    candidates: int,
) -> dict[str, float]:
    """Print recall@5 and MRR overall and by kind, and the hybrid noise."""
    scores = {m: metrics(runs, m) for m in METHODS}
    print(
        f"\n== recall@{K} [{label}] dataset={dataset.name}: {len(runs)} queries, "
        f"{len(dataset.corpus)} articles, rrf_k={rrf_k}, candidates={candidates}"
    )
    print(f"  {'':<38} recall@{K}   MRR")
    for method in METHODS:
        recall, mrr = scores[method]
        print(f"  {LABELS[method]:<38} {recall:.3f}    {mrr:.3f}")
    print("  by kind of query (recall@5):")
    for kind in sorted({r.kind for r in runs}):
        row = "  ".join(f"{m} {metrics_by_kind(runs, m)[kind][0]:.2f}" for m in METHODS)
        print(f"    {kind:<11} {row}")
    n = noise(runs)
    print(
        f"  hybrid noise: of {n.relevant_vector_hits} relevant vector top-{K} hits, "
        f"hybrid dropped {n.dropped_by_hybrid_vs_vector}; of "
        f"{n.relevant_fulltext_hits} relevant fulltext top-{K} hits, hybrid dropped "
        f"{n.dropped_by_hybrid_vs_fulltext}"
    )
    return {m: scores[m][0] for m in METHODS}


@dataclass
class SweepRow:
    prefix: bool
    rrf_k: int
    candidates: int
    runs: list[QueryRun]


def sweep(
    engine: Engine,
    dataset: Dataset,
    *,
    client: httpx.Client | None,
    url: str,
    defaults: tuple[bool, int, int] = (True, 60, 50),
) -> list[SweepRow]:
    """prefix on/off x rrf_k x candidates; only the prefix re-embeds the corpus."""
    rows: list[SweepRow] = []
    for prefix_on in (True, False):
        doc_prefix, query_prefix = PREFIXES[prefix_on]
        load_corpus(engine, dataset, doc_prefix=doc_prefix, client=client, url=url)
        embedder = make_embedder(query_prefix=query_prefix, client=client, url=url)
        for rrf_k in sorted({*GRID_RRF_K, defaults[1]}):
            for candidates in sorted({*GRID_CANDIDATES, defaults[2]}):
                runs = run_queries(
                    engine, dataset, embedder, rrf_k=rrf_k, candidates=candidates,
                    methods=("fulltext", "vector", "hybrid"),
                )  # fmt: skip
                rows.append(SweepRow(prefix_on, rrf_k, candidates, runs))
    return rows


def print_sweep(
    rows: Sequence[SweepRow], defaults: tuple[bool, int, int] = (True, 60, 50)
) -> None:
    """One line per combination, then which ones are a clear win over the defaults."""
    base = next(r for r in rows if (r.prefix, r.rrf_k, r.candidates) == defaults)
    print(
        f"\n== sweep over prefix x rrf_k x candidates ({len(rows)} rows), "
        f"defaults {defaults}"
    )
    print("  prefix rrf_k cand | vector rec  MRR  | hybrid rec  MRR")
    for r in rows:
        vr, vm = metrics(r.runs, "vector")
        hr, hm = metrics(r.runs, "hybrid")
        flag = "  <- defaults" if r is base else ""
        print(f"  {'on ' if r.prefix else 'off'}   {r.rrf_k:>5} {r.candidates:>4} |"
              f"   {vr:.3f} {vm:.3f} |   {hr:.3f} {hm:.3f}{flag}")  # fmt: skip
    wins = [
        (r, method)
        for r in rows
        if r is not base
        for method in ("vector", "hybrid")
        if clear_win(r.runs, base.runs, method)
    ]
    print(f"  clear wins over the defaults (ADR-0039 rule): {len(wins)}")
    for r, method in wins:
        print(f"    {method}: prefix={'on' if r.prefix else 'off'} rrf_k={r.rrf_k} "
              f"candidates={r.candidates}")  # fmt: skip
