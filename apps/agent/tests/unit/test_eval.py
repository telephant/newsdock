"""TC-28: the eval command prints precision, recall, F1 and confusion counts."""

import csv
from pathlib import Path

import pytest
from newsdock_agent.domain.evaluate import evaluate
from newsdock_agent.domain.score import Score
from newsdock_agent.eval import main


class KeywordScorer:
    """Deterministic fake with the production Score shape."""

    def score(self, title: str) -> Score | None:
        if "skip" in title:
            return None  # malformed model output
        relevant = "fed" in title.lower()
        return Score(relevant=relevant, score=0.9 if relevant else 0.1, reason="kw")


ROWS = [  # (title, label)  → tp, fn, fp-free negatives, one unscorable
    ("Fed raises rates", True),  # predicted 0.9 → TP
    ("Fed cuts again", True),  # TP
    ("Storm hits coast", True),  # predicted 0.1 → FN
    ("Celebrity gossip", False),  # TN
    ("fed watch midweek", False),  # FP
    ("skip me", True),  # unscorable → skipped
]


def test_evaluate_confusion_and_metrics() -> None:
    result = evaluate(KeywordScorer(), [(t, label) for t, label in ROWS], threshold=0.5)
    assert (result.tp, result.fp, result.tn, result.fn) == (2, 1, 1, 1)
    assert result.skipped == 1
    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == pytest.approx(2 / 3)
    assert result.f1 == pytest.approx(2 / 3)


def test_eval_command_prints_metrics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "title", "themes", "label"])
        for title, label in ROWS:
            writer.writerow(["https://e.com/x", title, "ECON_X", int(label)])

    import newsdock_agent.eval as eval_module

    monkeypatch.setattr(eval_module, "_build_scorer", lambda settings: KeywordScorer())
    assert main(["--labels", str(labels)]) == 0
    out = capsys.readouterr().out
    for token in ("precision", "recall", "f1", "tp", "fp", "tn", "fn", "skipped"):
        assert token in out
    assert "0.67" in out  # the metrics themselves are printed
