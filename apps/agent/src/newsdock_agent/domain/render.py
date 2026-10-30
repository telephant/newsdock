"""Markdown rendering of one digest (spec §5, design-detail §5). Pure: no I/O.

Layout: one `#` heading, one notice line, then one `##` section per theme in rank
order: a one-line summary and the linked stories. Everything that came from the
data or the model goes through `escape_text`, so no markup or HTML is produced.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime

from newsdock_agent.domain.articles import Article
from newsdock_agent.domain.stories import ThemePick
from newsdock_agent.domain.text import clean_text, encode_url, escape_text

NOTICE = (
    "> From headlines only. Summaries are written by a small local model and can "
    "be wrong; open the links."
)
UNAVAILABLE = "Summary unavailable."


def theme_label(code: str) -> str:
    return code.replace("_", " ")


def story_line(article: Article) -> str:
    title = escape_text(article.title) or escape_text(article.url)
    count = article.source_count
    parts = [f"- [{title}]({encode_url(article.url)})"]
    if article.domain:
        parts.append(escape_text(article.domain))
    parts.append(f"{count} source" if count == 1 else f"{count} sources")
    return " · ".join(parts)


def _since(now: datetime, since: datetime | None) -> str:
    if since is None:
        return "first run"
    if since.date() == now.date():
        return f"since {since:%H:%M}"
    return f"since {since:%m-%d %H:%M}"


def _section_heading(rank: int, pick: ThemePick) -> str:
    theme = pick.theme
    stories = "1 story" if theme.count == 1 else f"{theme.count} stories"
    how = "no baseline yet" if theme.rise is None else f"×{theme.rise:.1f} vs usual"
    return f"## {rank}. {theme_label(theme.code)} · {how} · {stories}"


def render_digest(
    *,
    now: datetime,
    article_count: int,
    since: datetime | None,
    picks: Sequence[ThemePick],
    summaries: Mapping[str, str | None],
) -> str:
    lines = [
        f"# What happened · {now:%Y-%m-%d %H:%M} UTC "
        f"({article_count} articles · {_since(now, since)})",
        "",
        NOTICE,
    ]
    rank = 0
    for pick in picks:
        if not pick.shown:  # every story of this theme was taken by a higher theme
            continue
        rank += 1
        summary = summaries.get(pick.theme.code)
        text = escape_text(summary) if summary and clean_text(summary) else UNAVAILABLE
        lines += ["", _section_heading(rank, pick), "", text]
        lines += [story_line(a) for a in pick.shown]
    return "\n".join(lines) + "\n"
