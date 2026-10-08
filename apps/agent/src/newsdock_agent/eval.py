"""Eval command (AC-14): `python -m newsdock_agent.eval --labels labels.csv`.

labels.csv is a self-contained snapshot (`url,title,themes,label`) because the
7-day store expires articles (design-detail §7). Scoring uses the production
prompt and structured-output schema; threshold from settings (default 0.5).
"""

import argparse
import csv
from pathlib import Path

from newsdock_config import load_settings

from newsdock_agent.adapters.ollama import OllamaScorer
from newsdock_agent.config import Settings
from newsdock_agent.domain.evaluate import evaluate
from newsdock_agent.domain.loop import ScorerPort


def _build_scorer(settings: Settings) -> ScorerPort:
    return OllamaScorer(
        settings.ollama_url,
        settings.model,
        timeout_seconds=settings.ollama_timeout_seconds,
        temperature=settings.ollama_temperature,
    )


def _load_labels(path: Path) -> list[tuple[str, bool]]:
    with path.open(newline="") as f:
        return [
            (row["title"], row["label"].strip().lower() in ("1", "true", "yes"))
            for row in csv.DictReader(f)
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    settings = load_settings(Settings)
    parser.add_argument("--threshold", type=float, default=settings.eval_threshold)
    args = parser.parse_args(argv)

    rows = _load_labels(args.labels)
    result = evaluate(_build_scorer(settings), rows, threshold=args.threshold)
    print(f"rows: {len(rows)}  threshold: {args.threshold}")
    print(
        f"tp: {result.tp}  fp: {result.fp}  tn: {result.tn}  "
        f"fn: {result.fn}  skipped: {result.skipped}"
    )
    print(f"precision: {result.precision:.2f}")
    print(f"recall: {result.recall:.2f}")
    print(f"f1: {result.f1:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
