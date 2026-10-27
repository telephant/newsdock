"""TC-16…TC-18: every app image builds, builds alone, and is safe (AC-8)."""

import re
import socket
import subprocess
import time
import urllib.request
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
def test_python_image_entrypoint_imports(app: str) -> None:  # TC-18
    """M0 asserted "default command prints and exits 0"; since M1 (T-04…T-08)
    the apps are long-running daemons needing env/Kafka/DB, so the image
    contract is now: the venv works and the entrypoint module imports."""
    result = run(
        "docker", "run", "--rm", "--entrypoint", "python",
        f"newsdock-{app}:dev", "-c", f"import newsdock_{app}.__main__",
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 (local)
        return int(response.status), response.read().decode("utf-8", "replace")


def test_web_image_ships_the_stylesheet() -> None:  # TC-20 (ui-design AC-14)
    """The served login page links a CSS file that exists in the image and holds
    the design tokens (Tailwind output), so the container is styled, not bare."""
    assert image_exists("web"), "run `make build APP=web` first"
    port = free_port()
    name = f"newsdock-web-style-{port}"
    started = run(
        "docker", "run", "-d", "--rm", "--name", name,
        "-p", f"127.0.0.1:{port}:3000", "newsdock-web:dev",
    )  # fmt: skip
    assert started.returncode == 0, started.stderr
    try:
        html = ""
        for _ in range(60):
            try:
                status, html = fetch(f"http://127.0.0.1:{port}/login")
                if status == 200:
                    break
            except OSError:
                time.sleep(0.5)
        assert html, "the web container never answered on /login"
        hrefs = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', html)
        hrefs += re.findall(r'<link[^>]+href="([^"]+\.css[^"]*)"', html)
        assert hrefs, f"no stylesheet link in the login page: {html[:300]}"
        status, css = fetch(f"http://127.0.0.1:{port}{hrefs[0]}")
        assert status == 200
        assert "--primary" in css
    finally:
        run("docker", "stop", name)
