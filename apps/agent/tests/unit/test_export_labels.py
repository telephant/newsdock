"""export_labels writes one row per distinct title (syndication dedup)."""

from pathlib import Path

import pytest
from newsdock_agent.export_labels import dedupe_by_title, main


def test_dedupe_keeps_first_of_each_title() -> None:
    articles: list[dict[str, object]] = [
        {"url": "https://a.com/1", "title": "Same story", "themes": ["ECON_X"]},
        {"url": "https://b.com/2", "title": "Same story", "themes": ["ECON_X"]},
        {"url": "https://c.com/3", "title": "Other story", "themes": []},
    ]
    out = dedupe_by_title(articles)
    assert [a["url"] for a in out] == ["https://a.com/1", "https://c.com/3"]


class _Response:
    def json(self) -> dict[str, object]:
        return {"articles": [{"url": "https://a.com/1", "title": "T", "themes": []}]}


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, api_key: str | None
) -> dict[str, object]:
    seen: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> _Response:
        seen.update(kwargs, url=url)
        return _Response()

    monkeypatch.setattr("newsdock_agent.export_labels.httpx.get", fake_get)
    monkeypatch.delenv("NEWSDOCK_AGENT_API_KEY", raising=False)
    if api_key:
        monkeypatch.setenv("NEWSDOCK_AGENT_API_KEY", api_key)
    assert main(["--out", str(tmp_path / "out.csv")]) == 0
    return seen


def test_export_sends_the_agent_key_because_reads_need_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = _run(monkeypatch, tmp_path, "ndk_abc_secret")
    assert seen["headers"] == {"Authorization": "Bearer ndk_abc_secret"}
    assert str(seen["url"]).endswith("/api/articles")


def test_export_without_a_key_sends_no_authorization_header(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _run(monkeypatch, tmp_path, None)["headers"] == {}
