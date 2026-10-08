"""TC-17 (agent half): Ollama timeout and temperature come from settings."""

import json

import httpx
from newsdock_agent.adapters.ollama import OllamaScorer


def test_timeout_and_temperature_reach_the_client_and_request() -> None:
    scorer = OllamaScorer(
        "http://ollama.test", "m", timeout_seconds=9.0, temperature=0.3
    )
    assert scorer._client.timeout.read == 9.0
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        content = '{"relevant": true, "score": 0.9, "reason": "r"}'
        return httpx.Response(200, json={"message": {"content": content}})

    scorer._client = httpx.Client(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    assert scorer.score("a title") is not None
    options = bodies[0]["options"]
    assert isinstance(options, dict) and options["temperature"] == 0.3
