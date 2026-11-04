"""TC-16 (AC-13): nothing of the theme digest is left, and an old environment that
still names its settings starts without error."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

from whathappen.adapters import files
from whathappen.adapters.files import DigestWriter
from whathappen.config import Settings
from whathappen.domain import prompt, render
from whathappen.domain.digest import DigestCycle, DigestParams
from whathappen.domain.grouping import LexicalGrouper
from whathappen.domain.titles import MatchParams

PROJECT = Path(__file__).resolve().parents[2]  # agents/whathappen

OLD_MODULES = ("themes", "baseline", "stories")
OLD_SETTINGS = (
    "max_themes",
    "stories_per_theme",
    "prompt_titles",
    "min_theme_count",
    "skip_theme_prefixes",
    "baseline_hours",
    "baseline_min_entries",
    "baseline_themes_kept",
    "state_file",
)
OLD_TEXT = (
    "vs usual",
    "no baseline yet",
    "BaselineStore",
    "ThemePick",
    "RankedTheme",
    "count_themes",
    "rank_themes",
    "pick_stories",
    "theme_prompt",
    "theme_label",
    "render_digest(",
    "skip_theme_prefixes",
    "min_theme_count",
    "max_themes",
    "stories_per_theme",
    "prompt_titles",
    "baseline_hours",
    "baseline_min_entries",
    "baseline_themes_kept",
    "STATE_FILE",
    "state_file",
    "state_path",
    "skip_prefixes",
)
# the files that may name the old things on purpose: this test, which defines them,
# and the cleanup command, which has to recognise the old baseline file
ALLOWED = {
    "tests/unit/test_removed.py",
    "src/whathappen/adapters/cleanup.py",
    "tests/unit/test_cleanup.py",
}


def scanned_files() -> list[Path]:
    wanted = [
        *PROJECT.glob("src/**/*.py"),
        *PROJECT.glob("tests/**/*.py"),
        PROJECT / "README.md",
        PROJECT / "Makefile",
        PROJECT / "compose.yaml",
        PROJECT / ".env.example",
        PROJECT / "Dockerfile",
        PROJECT / "pyproject.toml",
    ]
    return [
        p
        for p in wanted
        if p.is_file()
        and p.relative_to(PROJECT).as_posix() not in ALLOWED
        and "__pycache__" not in p.parts
    ]


@pytest.mark.parametrize("name", OLD_MODULES)
def test_the_old_modules_are_gone(name: str) -> None:
    assert importlib.util.find_spec(f"whathappen.domain.{name}") is None


def test_the_old_functions_are_gone() -> None:
    for module, names in (
        (render, ("render_digest", "story_line", "theme_label", "NOTICE")),
        (prompt, ("theme_prompt",)),
        (files, ("BaselineStore", "BASELINE_VERSION")),
    ):
        for name in names:
            assert not hasattr(module, name), f"{module.__name__}.{name} is still there"


def test_settings_have_no_theme_or_baseline_fields() -> None:
    for name in OLD_SETTINGS:
        assert name not in Settings.model_fields
    for name in ("skip_prefixes", "state_path"):
        assert not hasattr(Settings, name)


def test_no_text_of_the_theme_digest_remains() -> None:
    found = [
        f"{p.relative_to(PROJECT)}: {term}"
        for p in scanned_files()
        for term in OLD_TEXT
        if term in p.read_text(encoding="utf-8")
    ]
    assert found == []


def test_an_environment_that_still_sets_the_old_variables_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in OLD_SETTINGS:
        monkeypatch.setenv(f"WHATHAPPEN_{name.upper()}", "5")
    assert Settings().top_stories == 5  # an unrelated, current setting still reads

    env = tmp_path / ".env"
    env.write_text(
        "".join(f"WHATHAPPEN_{name.upper()}=7\n" for name in OLD_SETTINGS)
        + "WHATHAPPEN_MODEL=still-works\n"
    )
    for name in OLD_SETTINGS:
        monkeypatch.delenv(f"WHATHAPPEN_{name.upper()}")
    monkeypatch.setitem(Settings.model_config, "env_file", env)
    assert Settings().model == "still-works"


class OnePage:
    def __init__(self) -> None:
        self.acked: list[str] = []

    def list_new_articles(
        self, limit: int, cursor: str | None = None, include: object = None
    ) -> tuple[list[dict[str, object]], str]:
        if cursor is not None:
            return [], cursor
        page: list[dict[str, object]] = [
            {
                "article_id": f"id{i}",
                "title": f"Storm batters the northern coast overnight {word}",
                "url": f"https://outlet{i}.com/{i}",
                "domain": f"outlet{i}.com",
                "published_at": "2026-11-02T08:00:00Z",
                "source_count": 4,
            }
            for i, word in enumerate(("today", "tonight"))
        ]
        return page, "c1"

    def ack_cursor(self, cursor: str) -> None:
        self.acked.append(cursor)

    def get_article(self, article_id: str) -> dict[str, object]:
        return {"body_status": "none", "body": None}  # never called: grounding is off


class NoModel:
    def summarise(self, titles: object, excerpt: object = None) -> str | None:
        return None


def test_a_cycle_writes_only_the_digest_files_and_no_baseline(tmp_path: Path) -> None:
    out = tmp_path / "output"
    cycle = DigestCycle(
        OnePage(),
        LexicalGrouper(MatchParams(), __import__("datetime").timedelta(hours=48)),
        NoModel(),
        DigestWriter(out),
        DigestParams(
            page_size=200, max_articles=1000, min_group_sources=2, top_stories=5,
            max_sections=6, groups_per_section=4, also_per_group=3,
            section_min_hits=1, tone_divisor=10.0, labels=(),
        ),
    )  # fmt: skip
    assert cycle.run_once(datetime(2026, 11, 2, 9, 5, tzinfo=UTC)) is not None
    written = sorted(
        p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()
    )
    assert written == ["2026-11-02/0905.md", "latest.md"]
    assert not list(tmp_path.rglob("baseline*"))
