"""Markdown rendering of one digest (spec §5, design-detail §5). Pure: no I/O.

Layout: one `#` heading, one notice line, then one `##` section per theme in rank
order: a one-line summary and the linked stories. Everything that came from the
data or the model goes through `escape_text`, so no markup or HTML is produced.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime

from whathappen.domain.articles import Article
from whathappen.domain.scoring import RANKING_TONE, ScoredGroup
from whathappen.domain.sections import Selection
from whathappen.domain.stories import ThemePick
from whathappen.domain.text import clean_text, encode_url, escape_markdown, escape_text
from whathappen.domain.titles import clean_title

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


# ---- the story-first digest (spec digest-top-stories, design C-75) -----------------

MARKER = "<!-- whathappen:story-first -->"
_NOTICE_FIRST = (
    "> New this hour, from headlines only. Ranked by outlets covering a story"
)
_NOTICE_SECOND = (
    "> Summaries are written by a small local model and can be wrong; open the links."
)


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _link(article: Article) -> str:
    title = escape_markdown(clean_title(article.title)) or escape_text(article.url)
    return f"[{title}]({encode_url(article.url)})"


def _story_line(prefix: str, item: ScoredGroup) -> str:
    shown = item.group.shown
    parts = [f"{prefix}{_link(shown)}"]
    if shown.domain:
        parts.append(escape_text(shown.domain))
    parts.append(_count(item.sources, "source", "sources"))
    return " · ".join(parts)


def _story(
    prefix: str,
    indent: str,
    item: ScoredGroup,
    summaries: Mapping[str, str | None],
    also_limit: int,
) -> list[str]:
    group = item.group
    lines = [_story_line(prefix, item)]
    if len(group.variants) >= 2:  # one headline needs no model sentence
        summary = summaries.get(group.key)
        if summary and clean_text(summary):
            lines.append(indent + escape_text(summary))
    also = group.also[:also_limit]
    if also:
        lines.append(indent + "Also: " + ", ".join(_link(a) for a in also))
    return lines


def render_story_digest(
    *,
    now: datetime,
    article_count: int,
    selection: Selection,
    ranking: str,
    summaries: Mapping[str, str | None],
    min_sources: int,
    also_limit: int,
) -> str:
    """The whole file: marker, heading, notice, Top stories, labelled sections.

    Everything from the data or the model is cleaned and escaped as markdown text."""
    listed = len(selection.top) + sum(len(s.groups) for s in selection.sections)
    how = "." if ranking != RANKING_TONE else " and negative tone."
    lines = [
        MARKER,
        f"# What happened · {now:%Y-%m-%d %H:%M} UTC "
        f"({_count(article_count, 'new article', 'new articles')} · "
        f"{_count(listed, 'story', 'stories')})",
        "",
        _NOTICE_FIRST + how,
        _NOTICE_SECOND,
    ]
    if listed == 0:
        lines += [
            "",
            f"No story was carried by {min_sources} or more outlets this hour.",
        ]
        return "\n".join(lines) + "\n"
    if selection.top:
        lines += ["", "## Top stories"]
        for number, item in enumerate(selection.top, start=1):
            lines += _story(f"{number}. ", "   ", item, summaries, also_limit)
    for section in selection.sections:
        lines += ["", f"## {clean_text(section.label)}"]  # operator config, not data
        for item in section.groups:
            lines += _story("- ", "  ", item, summaries, also_limit)
    return "\n".join(lines) + "\n"
