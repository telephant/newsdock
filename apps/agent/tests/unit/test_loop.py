"""TC-29, TC-15 (M2): scoring parse/clamp/skip and ack-after-batch semantics."""

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
        self.acked: list[str] = []

    def list_new_articles(self, limit: int) -> tuple[list[dict[str, object]], str]:
        self.limits.append(limit)
        return list(ARTICLES), "cursor-2"

    def ack_cursor(self, cursor: str) -> None:
        self.acked.append(cursor)

    def submit_analysis(self, article_id: str, payload: dict[str, object]) -> None:
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


def loop(
    mcp: FakeMcp | None = None, scorer: FakeScorer | None = None
) -> tuple[AgentLoop, FakeMcp, FakeScorer]:
    mcp = mcp or FakeMcp()
    scorer = scorer or FakeScorer()
    return (
        AgentLoop(
            mcp,
            scorer,
            theme_prefixes=("ECON_",),
            batch_limit=200,
        ),
        mcp,
        scorer,
    )


# ---- pre-filter (spike decision: ECON_ only; empty themes skipped) ----------


def test_prefilter_scores_only_econ_articles() -> None:
    agent, mcp, scorer = loop()
    agent.run_once()
    assert scorer.scored == ["t0", "t3"]
    assert mcp.submitted == ["h0", "h3"]


def test_malformed_score_skips_article_without_crash() -> None:  # TC-29
    agent, mcp, scorer = loop(scorer=FakeScorer(malformed_on="t0"))
    agent.run_once()
    assert mcp.submitted == ["h3"]  # t0 skipped, loop continued
    assert mcp.acked == ["cursor-2"]  # batch still completed


# ---- TC-15: ack only after the whole batch succeeded ------------------------


def test_ack_sent_after_successful_batch() -> None:
    agent, mcp, _ = loop()
    agent.run_once()
    assert mcp.acked == ["cursor-2"]


def test_no_ack_when_a_submit_fails_mid_batch() -> None:
    agent, mcp, _ = loop(mcp=FakeMcp(fail_on="h3"))
    with pytest.raises(SubmitFailed):
        agent.run_once()
    assert mcp.acked == []  # batch is re-read next run
    assert mcp.submitted == ["h0"]  # crash mid-batch is harmless (upsert)


def test_no_ack_when_the_scorer_crashes() -> None:
    class Boom(FakeScorer):
        def score(self, title: str) -> Score | None:
            raise RuntimeError("ollama down")

    agent, mcp, _ = loop(scorer=Boom())
    with pytest.raises(RuntimeError):
        agent.run_once()
    assert mcp.acked == []


def test_loop_keeps_no_cursor_state_of_its_own() -> None:
    import importlib.util

    assert importlib.util.find_spec("newsdock_agent.adapters.cursor") is None


# ---- TC-17 (agent half): batch_limit comes from the constructor --------------


def test_tc17_batch_limit_is_passed_to_the_mcp_call() -> None:
    mcp = FakeMcp()
    agent = AgentLoop(
        mcp,
        FakeScorer(),
        theme_prefixes=("ECON_",),
        batch_limit=17,
    )
    agent.run_once()
    assert mcp.limits == [17]
