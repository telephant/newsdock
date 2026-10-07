"""export_labels writes one row per distinct title (syndication dedup)."""

from newsdock_agent.export_labels import dedupe_by_title


def test_dedupe_keeps_first_of_each_title() -> None:
    articles: list[dict[str, object]] = [
        {"url": "https://a.com/1", "title": "Same story", "themes": ["ECON_X"]},
        {"url": "https://b.com/2", "title": "Same story", "themes": ["ECON_X"]},
        {"url": "https://c.com/3", "title": "Other story", "themes": []},
    ]
    out = dedupe_by_title(articles)
    assert [a["url"] for a in out] == ["https://a.com/1", "https://c.com/3"]
