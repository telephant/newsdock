"""Pure evaluation: same scorer as production, threshold 0.5 (AC-14)."""

from dataclasses import dataclass

from newsdock_agent.domain.loop import ScorerPort

DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class EvalResult:
    tp: int
    fp: int
    tn: int
    fn: int
    skipped: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def evaluate(
    scorer: ScorerPort,
    rows: list[tuple[str, bool]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> EvalResult:
    tp = fp = tn = fn = skipped = 0
    for title, label in rows:
        score = scorer.score(title)
        if score is None:
            skipped += 1
            continue
        predicted = score.score >= threshold
        if predicted and label:
            tp += 1
        elif predicted and not label:
            fp += 1
        elif not predicted and not label:
            tn += 1
        else:
            fn += 1
    return EvalResult(tp=tp, fp=fp, tn=tn, fn=fn, skipped=skipped)
