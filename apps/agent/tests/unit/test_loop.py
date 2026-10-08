"""TC-29, TC-32: scoring parse/clamp/skip and cursor-after-batch semantics."""

import pytest
from newsdock_agent.domain.loop import AgentLoop, SubmitFailed
from newsdock_agent.domain.score import Score, parse_score

# ---- TC-29: structured output parsing --------------------------------------


def test_valid_output_parses() -> None:
    score = parse_score('{"relevant": true, "score": 0.8, "reason": "fed"}')
    assert score == Score(relevant=True, score=0.8, reason="fed")


def test_out_of_range_score_is_clamped() -> None:
    # spike.md: the grammar enforces shape, not bounds (llama once said 8.5)
    high = parse_score('{"relevant": true, "score": 8.5, "reason": "x"}')
    low = parse_score('{"relevant": false, "score": -2, "reason": "x"}')
    assert high is not None and high.score == 1.0
    assert low is not None and low.score == 0.0


def test_malformed_output_returns_none() -> None:
    assert parse_score("not json at all") is None
    assert parse_score('{"relevant": "maybe"}') is None


# ---- fakes ------------------------------------------------------------------


ARTICLES: list[dict[str, object]] = [
    {"article_id": f"h{i}", "title": f"t{i}", "themes": themes}
    for i, themes in enumerate(
        [["ECON_INFLATION"], ["ENV_CLIMATE"], [], ["ECON_TRADE", "TAX_X"]]
    )
]


class FakeMcp:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.submitted: list[str] = []
        self.limits: list[int] = []

    def list_new_articles(
        self, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, object]], str]:
        self.limits.append(limit)
        return list(ARTICLES), "cursor-2"

    def submit_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, object]
    ) -> None:
        if article_id == self.fail_on:
            raise SubmitFailed(article_id)
        self.submitted.append(article_id)


class FakeScorer:
    def __init__(self, malformed_on: str | None = None) -> None:
        self.malformed_on = malformed_on
        self.scored: list[str] = []

    def score(self, title: str) -> Score | None:
        self.scored.append(title)
        if self.malformed_on == title:
            return None
        return Score(relevant=True, score=0.9, reason="r")


class MemCursor:
    def __init__(self) -> None:
        self.value: str | None = None

    def load(self) -> str | None:
        return self.value

    def save(self, cursor: str) -> None:
        self.value = cursor


def loop(
    mcp: FakeMcp | None = None, scorer: FakeScorer | None = None
) -> tuple[AgentLoop, FakeMcp, FakeScorer, MemCursor]:
    mcp = mcp or FakeMcp()
    scorer = scorer or FakeScorer()
    cursor = MemCursor()
    return (
        AgentLoop(
            mcp,
            scorer,
            cursor,
            agent_name="demo",
            theme_prefixes=("ECON_",),
            batch_limit=200,
        ),
        mcp,
        scorer,
        cursor,
    )


# ---- pre-filter (spike decision: ECON_ only; empty themes skipped) ----------


def test_prefilter_scores_only_econ_articles() -> None:
    agent, mcp, scorer, _ = loop()
    agent.run_once()
    assert scorer.scored == ["t0", "t3"]
    assert mcp.submitted == ["h0", "h3"]


def test_malformed_score_skips_article_without_crash() -> None:  # TC-29
    agent, mcp, scorer, cursor = loop(scorer=FakeScorer(malformed_on="t0"))
    agent.run_once()
    assert mcp.submitted == ["h3"]  # t0 skipped, loop continued
    assert cursor.value == "cursor-2"  # batch still completed


# ---- TC-32: cursor saved only after the whole batch succeeded ---------------


def test_cursor_saved_after_successful_batch() -> None:
    agent, _, _, cursor = loop()
    agent.run_once()
    assert cursor.value == "cursor-2"


def test_cursor_unchanged_when_a_submit_fails_mid_batch() -> None:
    agent, mcp, _, cursor = loop(mcp=FakeMcp(fail_on="h3"))
    with pytest.raises(SubmitFailed):
        agent.run_once()
    assert cursor.value is None  # old cursor kept; batch re-scored next run
    assert mcp.submitted == ["h0"]  # crash mid-batch is harmless (upsert)


# ---- TC-17 (agent half): batch_limit comes from the constructor --------------


def test_tc17_batch_limit_is_passed_to_the_mcp_call() -> None:
    mcp = FakeMcp()
    agent = AgentLoop(
        mcp,
        FakeScorer(),
        MemCursor(),
        agent_name="demo",
        theme_prefixes=("ECON_",),
        batch_limit=17,
    )
    agent.run_once()
    assert mcp.limits == [17]
