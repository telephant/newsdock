"""Selection and sections (design C-74, spec D-5, D-8). Pure: no I/O.

Groups below the minimum coverage are not listed. The best few form the Top stories
block; every other group goes under a fixed, plain-language label chosen by a vote
over the GDELT theme codes of its articles. Theme codes are noisy on real data (a
company deal tagged ARMEDCONFLICT, a Houdini story tagged MEDICAL), so the label with
the most hits across the whole group wins, a label needs a minimum number of hits,
and the default map uses specific prefixes only. A group without a label goes to
"Other". A group is listed once.
"""

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from whathappen.domain.grouping import StoryGroup
from whathappen.domain.scoring import ScoredGroup

OTHER = "Other"

# label -> theme prefixes; the order of labels breaks ties between equal votes
SectionLabels = tuple[tuple[str, tuple[str, ...]], ...]

# Provisional, from the theme counts of real multi-source stories (spike.md). Generic
# codes that tag unrelated stories (EDUCATION, MANMADE_DISASTER_IMPLIED,
# SECURITY_SERVICES, KILL) are left out on purpose.
DEFAULT_SECTIONS: SectionLabels = (
    (
        "Conflict & Security",
        (
            "ARMEDCONFLICT",
            "MILITARY",
            "TERROR",
            "UNREST_BELLIGERENT",
            "CEASEFIRE",
            "EXTREMISM",
            "DRONES",
        ),
    ),
    (
        "Politics & Government",
        (
            "ELECTION",
            "LEGISLATION",
            "DEMOCRACY",
            "CONSTITUTIONAL",
            "NEGOTIATIONS",
            "ALLIANCE",
            "IMMIGRATION",
            "GOV_",
            "VETO",
            "RATIFY",
            "RESIGNATION",
            "SOVEREIGNTY",
        ),
    ),
    ("Business & Markets", ("ECON_", "FUELPRICES", "ENV_OIL", "STRIKE")),
    ("Crime & Courts", ("ARREST", "TRIAL", "CORRUPTION", "PROTEST")),
    ("Health", ("MEDICAL", "HEALTH", "DISEASE")),
    (
        "Disasters & Accidents",
        ("NATURAL_DISASTER", "EVACUATION", "MARITIME_INCIDENT", "TRAFFIC"),
    ),
)


def parse_section_labels(raw: str) -> SectionLabels:
    """A JSON object of label -> list of theme prefixes, in priority order."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"section_labels is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("section_labels must be a JSON object of label to prefixes")
    labels: list[tuple[str, tuple[str, ...]]] = []
    for name, prefixes in data.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("section_labels: every label must be a non-empty string")
        if name.strip().lower() == OTHER.lower():
            raise ValueError(
                f"section_labels: {OTHER!r} is reserved for unmatched groups"
            )
        if not isinstance(prefixes, list) or not all(
            isinstance(p, str) and p for p in prefixes
        ):
            raise ValueError(
                f"section_labels: {name!r} must map to a list of non-empty prefixes"
            )
        labels.append((name, tuple(prefixes)))
    return tuple(labels)


def label_for(group: StoryGroup, labels: SectionLabels, min_hits: int) -> str:
    """The label with the most theme hits across the group's articles.

    A hit is one theme occurrence starting with one of the label's prefixes (counted
    once per label even if two prefixes match). Ties go to the label listed first; a
    best count below `min_hits`, or no hit at all, means "Other"."""
    votes: Counter[str] = Counter()
    for member in group.members:
        for theme in member.themes:
            for name, prefixes in labels:
                if theme.startswith(prefixes):
                    votes[name] += 1
    if not votes:
        return OTHER
    best = max(votes.values())
    if best < min_hits:
        return OTHER
    for name, _ in labels:
        if votes.get(name) == best:
            return name
    return OTHER


@dataclass(frozen=True)
class SelectParams:
    top_stories: int
    max_sections: int
    groups_per_section: int
    min_group_sources: int
    section_min_hits: int
    labels: SectionLabels


@dataclass(frozen=True)
class Section:
    label: str
    groups: tuple[ScoredGroup, ...]


@dataclass(frozen=True)
class Selection:
    top: tuple[ScoredGroup, ...]
    sections: tuple[Section, ...]


def select(scored: Sequence[ScoredGroup], params: SelectParams) -> Selection:
    """Split best-first scored groups into the Top block and the labelled sections."""
    qualifying = [s for s in scored if s.sources >= params.min_group_sources]
    top = qualifying[: params.top_stories]
    by_label: dict[str, list[ScoredGroup]] = {}
    for item in qualifying[params.top_stories :]:
        label = label_for(item.group, params.labels, params.section_min_hits)
        by_label.setdefault(label, []).append(item)  # first seen = best score first
    sections = tuple(
        Section(label, tuple(items[: params.groups_per_section]))
        for label, items in list(by_label.items())[: params.max_sections]
    )
    return Selection(top=tuple(top), sections=sections)
