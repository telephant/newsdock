"""A fake Ollama for tests in this package and in the apps that embed.

Lives in the package (not in a test folder) because apps may not import each
other's tests. Deterministic: the same text always gets the same vector.
"""

import hashlib
import json
import math

import httpx


class FakeOllama:
    """Answers `POST /api/embed`; `requests` records the calls.

    `mode` picks the behaviour: ok, refuse (connection error), timeout, http500,
    missing (404 model not found), bad_json, short_list (one vector too few),
    short_vector (wrong length), nan (a NaN value).
    """

    def __init__(
        self, *, dimension: int = 768, mode: str = "ok", body: str = "boom"
    ) -> None:
        self.dimension = dimension
        self.mode = mode
        self.body = body
        self.requests: list[httpx.Request] = []

    def vector_for(self, text: str) -> list[float]:
        """A deterministic unit vector derived from the text."""
        raw: list[float] = []
        counter = 0
        while len(raw) < self.dimension:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            raw.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        raw = raw[: self.dimension]
        norm = math.sqrt(sum(value * value for value in raw)) or 1.0
        return [value / norm for value in raw]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.mode == "refuse":
            raise httpx.ConnectError("connection refused", request=request)
        if self.mode == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if self.mode == "http500":
            return httpx.Response(500, text=self.body)
        if self.mode == "missing":
            model = json.loads(request.content).get("model", "?")
            error = f'model "{model}" not found, try pulling it first'
            return httpx.Response(404, json={"error": error})
        if self.mode == "bad_json":
            return httpx.Response(200, text="<html>not json</html>")
        texts: list[str] = json.loads(request.content)["input"]
        vectors = [self.vector_for(text) for text in texts]
        if self.mode == "short_list":
            vectors = vectors[:-1]
        elif self.mode == "short_vector":
            vectors = [vector[:-1] for vector in vectors]
        elif self.mode == "nan":
            vectors = [[float("nan"), *vector[1:]] for vector in vectors]
        # JSON has no NaN; httpx's json= would raise, so encode with allow_nan.
        return httpx.Response(
            200,
            content=json.dumps({"embeddings": vectors}, allow_nan=True).encode(),
            headers={"content-type": "application/json"},
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)
