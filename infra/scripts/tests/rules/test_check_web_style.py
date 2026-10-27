"""TC-2, TC-3, TC-16, TC-17: web colours come from tokens and the tokens are readable
(ui-design AC-2, AC-11)."""

from pathlib import Path

import pytest

from .conftest import ROOT, output, run

pytestmark = pytest.mark.rules

SCRIPT = "infra/scripts/check_web_style.py"

GOOD_CSS = """\
:root {
  --background: #ffffff;
  --foreground: #111111;
  --card: #ffffff;
  --card-foreground: #111111;
  --muted-foreground: #555555;
  --primary: #06c755;
  --primary-foreground: #052e14;
  --primary-text: #047a37;
  --destructive: #b91c1c;
  --destructive-foreground: #ffffff;
  --ring: #047a37;
}
.dark {
  --background: #0f1210;
  --foreground: #eef2ef;
  --card: #151a17;
  --card-foreground: #eef2ef;
  --muted-foreground: #9aa8a0;
  --primary: #06c755;
  --primary-foreground: #052e14;
  --primary-text: #4ade80;
  --destructive: #f87171;
  --destructive-foreground: #1a0505;
  --ring: #4ade80;
}
"""


def make_tree(tmp_path: Path, css: str = GOOD_CSS, **sources: str) -> Path:
    src = tmp_path / "apps" / "web" / "src"
    (src / "app").mkdir(parents=True)
    (src / "app" / "globals.css").write_text(css)
    for name, text in sources.items():
        path = src / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def check(root: Path) -> tuple[int, str]:
    result = run("uv", "run", "python", SCRIPT, str(root))
    return result.returncode, output(result)


def test_real_tree_passes() -> None:  # TC-2, TC-16
    result = run("uv", "run", "python", SCRIPT)
    assert result.returncode == 0, output(result)


def test_clean_fixture_passes(tmp_path: Path) -> None:
    code, text = check(
        make_tree(tmp_path, **{"features__a.tsx": '<p className="bg-card" />'})
    )
    assert code == 0, text


@pytest.mark.parametrize(
    ("snippet", "needle"),
    [
        ('<p className="bg-green-500" />', "bg-green-500"),
        ('<p style={{ color: "#06c755" }} />', "#06c755"),
        ('<p style={{ color: "rgb(0, 0, 0)" }} />', "rgb("),
        ('<p className="text-[#fff]" />', "#fff"),
        ("<p dangerouslySetInnerHTML={{ __html: x }} />", "dangerouslySetInnerHTML"),
    ],
)
def test_colour_literals_and_raw_html_fail(  # TC-3
    tmp_path: Path, snippet: str, needle: str
) -> None:
    root = make_tree(tmp_path, **{"features__bad.tsx": snippet})
    code, text = check(root)
    assert code != 0
    assert "features/bad.tsx" in text and needle in text


def test_generated_ui_and_tests_are_exempt(tmp_path: Path) -> None:
    root = make_tree(
        tmp_path,
        **{
            "components__ui__x.tsx": '<p className="bg-green-500" />',
            "features__a.test.tsx": 'expect(el).toHaveClass("bg-green-500")',
            "lib__api__types.ts": "export type X = '#fff'",
        },
    )
    code, text = check(root)
    assert code == 0, text


def test_comments_may_mention_the_rules(tmp_path: Path) -> None:
    root = make_tree(
        tmp_path,
        **{
            "features__a.tsx": "// never use dangerouslySetInnerHTML or #fff here\n"
            "/* bg-green-500 */\n * rgb(0, 0, 0)\n<p />",
        },
    )
    code, text = check(root)
    assert code == 0, text


def test_low_contrast_pair_fails(tmp_path: Path) -> None:  # TC-17
    bad = GOOD_CSS.replace(
        "--muted-foreground: #555555", "--muted-foreground: #dddddd", 1
    )
    code, text = check(make_tree(tmp_path, css=bad))
    assert code != 0
    assert "muted-foreground" in text and "light" in text


def test_low_contrast_in_dark_theme_fails(tmp_path: Path) -> None:  # TC-17
    bad = GOOD_CSS.replace("--primary-text: #4ade80", "--primary-text: #1f3a2a", 1)
    code, text = check(make_tree(tmp_path, css=bad))
    assert code != 0
    assert "primary-text" in text and "dark" in text


def test_weak_focus_ring_fails(tmp_path: Path) -> None:  # TC-17
    bad = GOOD_CSS.replace("--ring: #047a37", "--ring: #f4f4f4", 1)
    code, text = check(make_tree(tmp_path, css=bad))
    assert code != 0
    assert "ring" in text


def test_missing_token_fails(tmp_path: Path) -> None:
    bad = GOOD_CSS.replace("  --primary-text: #047a37;\n", "", 1)
    code, text = check(make_tree(tmp_path, css=bad))
    assert code != 0
    assert "primary-text" in text


def test_script_lives_where_the_rules_expect() -> None:
    assert (ROOT / SCRIPT).is_file()
