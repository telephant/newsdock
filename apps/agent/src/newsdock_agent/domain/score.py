"""Score contract: {relevant, score 0–1, reason} (CLAUDE.md fixed names).

The structured-output grammar enforces shape, not numeric bounds (spike.md),
so the prompt states the range and parsing clamps; anything unparseable is
None (logged and skipped by the loop, never a crash — TC-29).
"""

import json

from pydantic import BaseModel, ValidationError

PROMPT = (
    "You classify news headlines by financial-market relevance.\n"
    "relevant=true when the headline concerns: company business actions "
    "(deals, M&A, tender offers, contracts, product launches, executives, "
    "restructuring), stock/bond/commodity markets, the macroeconomy, taxes or "
    "regulation, central banks, or trade policy.\n"
    "relevant=false for: sport, entertainment, celebrities, crime, accidents, "
    "weather, health and science (unless there is a company or market angle), "
    "and politics without economic substance.\n"
    "score is your confidence that it is relevant, as a decimal between 0.0 "
    "and 1.0: 0.9+ clearly relevant, ~0.6 probably, ~0.3 unlikely, 0.0 "
    "clearly not.\n"
    "Examples:\n"
    '"Acme Corp launches takeover bid for rival" -> relevant=true, score=0.95\n'
    '"Regulator fines bank over reporting failures" -> relevant=true, score=0.8\n'
    '"Pop star announces world tour" -> relevant=false, score=0.0\n'
    'Headline: "{title}"'
)

OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["relevant", "score", "reason"],
}


class Score(BaseModel):
    relevant: bool
    score: float
    reason: str


def parse_score(raw: str) -> Score | None:
    try:
        data = json.loads(raw)
        score = Score.model_validate(data)
    except (ValidationError, ValueError):
        return None
    return score.model_copy(update={"score": min(max(score.score, 0.0), 1.0)})
