"""Build the hard search eval queries from the frozen M3f fixture (hybrid-eval-set).

Offline and deterministic: it reads `search_eval_corpus.json` and
`search_eval_queries.json`, makes entity and low-overlap queries with the pure functions
in `search_eval_build.py`, and writes `search_eval_hard_queries.json`. No network, no
model, no clock in the output, so two runs give identical bytes:

    make eval-search-build-hard
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import search_eval_build as build

FIXTURES = Path(__file__).resolve().parents[2] / "packages/core/tests/fixtures"
SOURCES = ("search_eval_corpus.json", "search_eval_queries.json")


def dump_lines(items: list[dict[str, Any]]) -> str:
    """A JSON list with one item per line, so a rebuild gives a readable diff."""
    rows = ",\n".join(" " + json.dumps(i, ensure_ascii=False) for i in items)
    return f"[\n{rows}\n]\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures", type=Path, default=FIXTURES)
    ap.add_argument(
        "--out", type=Path, default=FIXTURES / "search_eval_hard_queries.json"
    )
    args = ap.parse_args(argv)

    corpus = json.loads((args.fixtures / SOURCES[0]).read_text(encoding="utf-8"))
    queries = json.loads((args.fixtures / SOURCES[1]).read_text(encoding="utf-8"))
    rows = build.build_hard_queries(corpus, queries["queries"])
    build.check_hard_fixture(corpus, rows)
    kinds = {
        k: sum(1 for r in rows if r["kind"] == k) for k in ("entity", "lowoverlap")
    }
    if not all(kinds.values()):
        print(f"a kind has no queries: {kinds}", file=sys.stderr)
        return 1
    header = {
        "from": list(SOURCES),
        "grade_overlap": build.GRADE_OVERLAP,
        "max_names": 3,
    }
    args.out.write_text(
        json.dumps({"built": header}, ensure_ascii=False)[:-1]
        + ', "queries": '
        + dump_lines(rows).rstrip("\n")
        + "}\n",
        encoding="utf-8",
    )
    print(f"hard queries {len(rows)} {kinds}; {args.out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
