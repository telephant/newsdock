"""Labelling helper: export a sample from the store (REST) to a CSV to label.

`python -m newsdock_agent.export_labels --out sample.csv [--limit 100]`
Writes `url,title,themes,label` with `label` empty, to fill by hand (AC-14).
Syndicated stories (same title on many sites) are exported once: labels judge
titles, so duplicates would waste labelling effort and skew the metrics.
The REST base comes from MCP_URL's host (the agent knows no other endpoint).
"""

import argparse
import csv
from pathlib import Path

import httpx
from newsdock_config import load_settings

from newsdock_agent.config import Settings


def dedupe_by_title(
    articles: list[dict[str, object]],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for article in articles:
        title = str(article["title"])
        if title not in seen:
            seen.add(title)
            out.append(article)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    settings = load_settings(Settings)
    parser.add_argument("--limit", type=int, default=settings.export_limit)
    args = parser.parse_args(argv)

    base = settings.mcp_url.removesuffix("/mcp")
    articles = dedupe_by_title(
        httpx.get(
            f"{base}/api/articles",
            params={"limit": args.limit},
            timeout=settings.export_timeout_seconds,
        ).json()["articles"]
    )
    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "themes", "label"])
        for a in articles:
            themes = a.get("themes")
            themes_text = (
                ";".join(str(t) for t in themes) if isinstance(themes, list) else ""
            )
            writer.writerow([a["url"], a["title"], themes_text, ""])
    print(f"wrote {len(articles)} rows to {args.out}; fill the label column (0/1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
