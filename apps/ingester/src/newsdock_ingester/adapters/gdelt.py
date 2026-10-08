"""HTTP source for GDELT; follows redirects (http:// 301s to https://)."""

import logging

import httpx

logger = logging.getLogger(__name__)


class HttpGdeltSource:
    def __init__(
        self, base_url: str, *, timeout_seconds: float, index_path: str
    ) -> None:
        self.base_url = base_url
        self._index_path = index_path
        self._client = httpx.Client(follow_redirects=True, timeout=timeout_seconds)

    def fetch_index(self) -> str | None:
        try:
            response = self._client.get(f"{self.base_url}{self._index_path}")
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("index fetch failed: %s", exc)
            return None

    def fetch_gkg(self, url: str) -> bytes | None:
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("gkg fetch failed: %s", exc)
            return None
        if response.status_code != 200 or not response.content:
            return None  # 404 or empty body: retry later (spec §3)
        return response.content
