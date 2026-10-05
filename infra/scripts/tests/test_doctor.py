"""TC-1…TC-3: doctor.sh reports missing tools and an unreachable Docker daemon."""

import json
import shutil
import stat
import subprocess
from pathlib import Path

DOCTOR = Path(__file__).resolve().parents[1] / "doctor.sh"

DOCKER = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "Docker version 29.0.0"; exit 0; fi
if [ "$1" = "compose" ]; then echo "Docker Compose version v5.0.0"; exit 0; fi
if [ "$1" = "info" ]; then
  if [ -n "$STUB_DOCKER_DOWN" ]; then echo "cannot connect" >&2; exit 1; fi
  echo "29.0.0"; exit 0
fi
"""
UV = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "uv 0.0.1"; exit 0; fi
if [ "$1" = "python" ]; then echo "{python}"; exit 0; fi
"""
PNPM = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "12.0.0"; fi\n'
OLLAMA = """#!/bin/sh
if [ "$1" = "list" ]; then
  echo "NAME ID SIZE MODIFIED"
  if [ -n "$STUB_OLLAMA_MODEL" ]; then echo "$STUB_OLLAMA_MODEL abc 1GB now"; fi
  exit 0
fi
echo "ollama version is 0.0.1"
"""
PYTHON = '#!/bin/sh\necho "Python 3.12.9"\n'


def stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


UTILITIES = ["awk", "grep", "sed", "tr", "head", "dirname", "cat"]


def stub_path(bin_dir: Path) -> str:
    """PATH for doctor.sh in tests: stubs and symlinked basics only, no /usr/bin."""
    return str(bin_dir)


def make_bin(tmp: Path, tools: list[str]) -> Path:
    directory = tmp / "bin"
    directory.mkdir()
    for utility in UTILITIES:
        found = shutil.which(utility)
        assert found, f"{utility} is needed by doctor.sh"
        (directory / utility).symlink_to(found)
    stub(directory, "python3.12", PYTHON)
    scripts = {
        "docker": DOCKER,
        "uv": UV.format(python=directory / "python3.12"),
        "pnpm": PNPM,
        "ollama": OLLAMA,
    }
    for tool in tools:
        stub(directory, tool, scripts[tool])
    return directory


def run_doctor(
    bin_dir: Path, root: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": stub_path(bin_dir), "DOCTOR_ROOT": str(root)}
    env.update(extra_env or {})
    return subprocess.run(
        ["/bin/bash", str(DOCTOR)], env=env, capture_output=True, text=True, check=False
    )


ALL = ["docker", "uv", "pnpm", "ollama"]


def test_missing_pnpm_is_named_with_install_hint(tmp_path: Path) -> None:  # TC-1
    result = run_doctor(make_bin(tmp_path, ["docker", "uv", "ollama"]), tmp_path)
    text = result.stdout + result.stderr
    assert result.returncode == 1
    assert "MISSING pnpm" in text
    assert "brew install pnpm" in text


def test_all_missing_tools_are_listed_in_one_run(tmp_path: Path) -> None:  # TC-2
    result = run_doctor(make_bin(tmp_path, ["pnpm", "ollama"]), tmp_path)
    text = result.stdout + result.stderr
    assert result.returncode == 1
    assert "MISSING docker" in text and "MISSING uv" in text


def test_unreachable_docker_daemon_fails(tmp_path: Path) -> None:  # TC-3
    result = run_doctor(
        make_bin(tmp_path, ALL), tmp_path, extra_env={"STUB_DOCKER_DOWN": "1"}
    )
    text = (result.stdout + result.stderr).lower()
    assert result.returncode == 1
    assert "daemon" in text and "not reachable" in text


def test_happy_path_prints_versions_python_node_and_models(tmp_path: Path) -> None:
    web = tmp_path / "apps" / "web"
    web.mkdir(parents=True)
    dev_engines = {"devEngines": {"runtime": {"name": "node", "version": "24.x"}}}
    (web / "package.json").write_text(json.dumps(dev_engines))
    result = run_doctor(
        make_bin(tmp_path, ALL),
        tmp_path,
        extra_env={"STUB_OLLAMA_MODEL": "tiny:1b"},
    )
    text = result.stdout
    assert result.returncode == 0, text + result.stderr
    for expected in ("Docker version 29.0.0", "Compose version v5.0.0", "uv 0.0.1"):
        assert expected in text
    assert "12.0.0" in text
    assert "Python 3.12.9" in text
    assert "24.x" in text
    assert "tiny:1b" in text


def test_ollama_without_a_model_warns_but_passes(tmp_path: Path) -> None:
    result = run_doctor(make_bin(tmp_path, ALL), tmp_path)
    assert result.returncode == 0
    assert "no model" in result.stdout.lower()


def test_node_is_not_required_on_path(tmp_path: Path) -> None:
    result = run_doctor(make_bin(tmp_path, ALL), tmp_path)
    assert "MISSING node" not in result.stdout + result.stderr
    assert "scaffolded" in result.stdout.lower() or "node" in result.stdout.lower()


def test_stub_path_cannot_see_system_tools(tmp_path: Path) -> None:
    """CI runners ship a real /usr/bin/docker: the test PATH must hold stubs only."""
    bin_dir = make_bin(tmp_path, ["pnpm"])
    path = stub_path(bin_dir)
    assert "/usr/bin" not in path.split(":")
    probe = subprocess.run(
        ["/bin/bash", "-c", "command -v docker"],
        env={"PATH": path},
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode != 0
