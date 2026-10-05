"""TC-16…TC-18: every app image builds, builds alone, and is safe (AC-8)."""

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[3]
APPS = ["ingester", "processor", "sink", "api", "agent", "web"]
PYTHON_APPS = [app for app in APPS if app != "web"]


def run(*cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd), cwd=ROOT, capture_output=True, text=True, check=False
    )


def image_exists(app: str) -> bool:
    return run("docker", "image", "inspect", f"newsdock-{app}:dev").returncode == 0


def test_make_build_builds_all_six_images_without_env_file() -> None:  # TC-16
    env, backup = ROOT / ".env", ROOT / ".env.pre-test"
    if env.exists():
        env.rename(backup)
    try:
        result = run("make", "build")
    finally:
        if backup.exists():
            backup.rename(env)
    assert result.returncode == 0, result.stdout + result.stderr
    for app in APPS:
        assert image_exists(app), f"newsdock-{app}:dev missing"


def test_make_build_with_app_builds_only_that_image() -> None:  # TC-17
    run("docker", "rmi", "-f", "newsdock-api:dev", "newsdock-sink:dev")
    result = run("make", "build", "APP=api")
    assert result.returncode == 0, result.stdout + result.stderr
    assert image_exists("api")
    assert not image_exists("sink")
    assert run("make", "build", "APP=sink").returncode == 0  # restore for later tests


@pytest.mark.parametrize("app", APPS)
def test_image_runs_as_non_root_and_holds_no_env_file(app: str) -> None:  # TC-18
    uid = run(
        "docker", "run", "--rm", "--entrypoint", "id", f"newsdock-{app}:dev", "-u"
    )
    assert uid.returncode == 0, uid.stderr
    assert uid.stdout.strip() != "0"
    listing = run(
        "docker", "run", "--rm", "--entrypoint", "find", f"newsdock-{app}:dev",
        "/", "-name", ".env*", "-not", "-path", "/proc/*", "-not", "-path", "/sys/*",
    )  # fmt: skip
    assert ".env" not in listing.stdout.replace("/.env.example", ""), listing.stdout


@pytest.mark.parametrize("app", PYTHON_APPS)
def test_python_image_default_command_exits_zero(app: str) -> None:  # TC-18
    result = run("docker", "run", "--rm", f"newsdock-{app}:dev")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"newsdock-{app}" in result.stdout
