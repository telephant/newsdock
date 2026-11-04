"""Build the search eval fixture from real GDELT slots (M3f, ADR-0039). Run by hand.

Needs the network (GDELT, once, cached) and Ollama with a chat model; it is never part
of CI or `make check`. The logic is in `search_eval_build.py` (pure, tested); this file
only fetches slots, calls Ollama and writes the two fixture files:

    make eval-search-build            # defaults: 8 slots, llama3.2:3b
"""

import argparse
import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import search_eval_build as build
from newsdock_core.contracts import CleanArticle, CleanMention
from newsdock_core.gkg import parse_row
from newsdock_core.mentions import parse_mention_row

GDELT = "http://data.gdeltproject.org/gdeltv2"
FILES = {"gkg": "gkg.csv.zip", "mentions": "mentions.CSV.zip"}
FIXTURES = Path(__file__).resolve().parents[2] / "packages/core/tests/fixtures"
PROMPTS = {
    "paraphrase": (
        "Here is a news headline:\n{title}\n\nWrite one short search query (4 to 10 "
        "words) that a reader could type to find news about the same event. Do not "
        "copy the headline and avoid its distinctive words. Reply with the query only."
    ),
    "keywords": (
        "Here is a news headline:\n{title}\n\nWrite 2 to 4 keywords (names and topics, "
        "not copied sentences) a reader could search to find news about the same "
        "event. Reply with the keywords only, separated by spaces."
    ),
}


def slot_list(end: str, count: int) -> list[str]:
    """`count` consecutive 15-minute slot ids ending at `end` (`YYYYMMDDHHMMSS`)."""
    last = datetime.strptime(end, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return [
        (last - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
        for i in reversed(range(count))
    ]


def fetch(slot: str, kind: str, cache: Path) -> str | None:
    """One slot file as text, cached; None when missing or not a valid zip."""
    target = cache / f"{slot}.{kind}.txt"
    if target.exists():
        return target.read_text(encoding="utf-8")
    url = f"{GDELT}/{slot}.{FILES[kind]}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                url, timeout=120
            ) as response:  # follows redirects
                data = response.read()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                text = archive.read(archive.namelist()[0]).decode("utf-8", "replace")
        except (urllib.error.URLError, zipfile.BadZipFile, OSError) as exc:
            print(
                f"  {slot} {kind}: attempt {attempt + 1} failed ({exc})",
                file=sys.stderr,
            )
            continue
        target.write_text(text, encoding="utf-8")
        return text
    return None


def load_slots(
    slots: list[str], cache: Path
) -> tuple[list[CleanArticle], list[CleanMention]]:
    articles: dict[str, CleanArticle] = {}
    mentions: list[CleanMention] = []
    for slot in slots:
        gkg, men = fetch(slot, "gkg", cache), fetch(slot, "mentions", cache)
        if gkg is None or men is None:
            print(f"  slot {slot}: skipped (missing)", file=sys.stderr)
            continue
        for n, line in enumerate(gkg.splitlines()):
            parsed = parse_row(slot=slot, row_no=n, line=line)
            if isinstance(parsed, CleanArticle):
                articles.setdefault(parsed.url_hash, parsed)
        for n, line in enumerate(men.splitlines()):
            mention = parse_mention_row(slot=slot, row_no=n, line=line)
            if isinstance(mention, CleanMention):
                mentions.append(mention)
    return list(articles.values()), mentions


def ollama_chat(url: str, model: str, kind: str, title: str) -> str:
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0, "seed": 1},
        "messages": [{"role": "user", "content": PROMPTS[kind].format(title=title)}],
    }
    request = urllib.request.Request(
        f"{url}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        reply: dict[str, Any] = json.load(response)
    return str(reply["message"]["content"])


JUDGE_PROMPT = (
    "Headline A: {a}\nHeadline B: {b}\n\nAre A and B about the same specific news "
    "story or event (not just the same general topic, place or day)? Answer with one "
    "word: yes or no."
)


def ollama_judge(url: str, model: str, seed_title: str, member_title: str) -> bool:
    """True when the model answers yes to 'same story?' (temperature 0)."""
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0, "seed": 1},
        "messages": [
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(a=seed_title, b=member_title),
            }
        ],
    }
    request = urllib.request.Request(
        f"{url}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        reply: dict[str, Any] = json.load(response)
    return str(reply["message"]["content"]).strip().casefold().startswith("yes")


def dump_lines(items: list[dict[str, Any]]) -> str:
    """A JSON list with one item per line, so a rebuild gives a readable diff."""
    rows = ",\n".join(" " + json.dumps(i, ensure_ascii=False) for i in items)
    return f"[\n{rows}\n]\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--end-slot", default="20261104084500")
    ap.add_argument("--slots", type=int, default=8)
    ap.add_argument("--max-clusters", type=int, default=600)
    ap.add_argument("--distractors", type=int, default=300)
    ap.add_argument("--min-clusters", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--out", type=Path, default=FIXTURES)
    ap.add_argument(
        "--cache",
        type=Path,
        default=Path(tempfile.gettempdir()) / "newsdock-search-eval",
    )
    args = ap.parse_args(argv)

    args.cache.mkdir(parents=True, exist_ok=True)
    slots = slot_list(args.end_slot, args.slots)
    articles, mentions = load_slots(slots, args.cache)
    reps, rep_of = build.collapse(articles)
    clusters = build.drop_roundups(build.derive_clusters(rep_of, mentions))
    print(f"slots {slots[0]}..{slots[-1]}: {len(articles)} articles, "
          f"{len(reps)} after collapsing, {len(mentions)} mentions, "
          f"{len(clusters)} clusters")  # fmt: skip
    if len(clusters) < args.min_clusters:
        floor = args.min_clusters
        print(
            f"only {len(clusters)} clusters (floor {floor}): widen --slots",
            file=sys.stderr,
        )
        return 1

    def chat(kind: str, title: str) -> str:
        return ollama_chat(args.ollama_url, args.model, kind, title)

    judgments: list[str] = []

    def judge(seed_title: str, member_title: str) -> bool:
        said = ollama_judge(args.ollama_url, args.model, seed_title, member_title)
        judgments.append(f"{'yes' if said else 'no'}\t{seed_title}\t{member_title}")
        return said

    corpus, queries = build.assemble(
        reps, mentions, chat, judge, max_clusters=args.max_clusters,
        distractors=args.distractors, rng_seed=args.seed,
    )  # fmt: skip
    build.check_fixture(corpus, queries)
    audit = args.cache / "judgments.tsv"
    audit.write_text("\n".join(judgments) + "\n", encoding="utf-8")
    print(f"judge said yes to {sum(j.startswith('yes') for j in judgments)} of "
          f"{len(judgments)} pairs; audit file {audit}")  # fmt: skip
    kinds = {k: sum(1 for q in queries if q["kind"] == k) for k in build.KINDS}
    header = {"slots": [slots[0], slots[-1]], "model": args.model, "seed": args.seed,
              "built": datetime.now(UTC).strftime("%Y-%m-%d")}  # fmt: skip
    args.out.mkdir(parents=True, exist_ok=True)
    corpus_path = args.out / "search_eval_corpus.json"
    queries_path = args.out / "search_eval_queries.json"
    corpus_path.write_text(dump_lines(corpus), encoding="utf-8")
    queries_path.write_text(
        json.dumps({"built": header}, ensure_ascii=False)[:-1]
        + ', "queries": '
        + dump_lines(queries).rstrip("\n")
        + "}\n",
        encoding="utf-8",
    )
    kb = {p.name: p.stat().st_size // 1024 for p in (corpus_path, queries_path)}
    print(
        f"corpus {len(corpus)} articles, queries {len(queries)} {kinds}; size KB {kb}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
