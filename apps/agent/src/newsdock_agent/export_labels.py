"""Labelling helper: export a sample from the store (REST) to a CSV to label.

`python -m newsdock_agent.export_labels --out sample.csv [--limit 100]`
Writes `url,title,themes,label` with `label` empty, to fill by hand (AC-14).
The REST base comes from MCP_URL's host (the agent knows no other endpoint).
"""

import argparse
import csv
from pathlib import Path

import httpx

from newsdock_agent.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)

    base = Settings().mcp_url.removesuffix("/mcp")
    articles = httpx.get(
        f"{base}/api/articles", params={"limit": args.limit}, timeout=30
    ).json()["articles"]
    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "themes", "label"])
        for a in articles:
            writer.writerow([a["url"], a["title"], ";".join(a["themes"]), ""])
    print(f"wrote {len(articles)} rows to {args.out}; fill the label column (0/1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
