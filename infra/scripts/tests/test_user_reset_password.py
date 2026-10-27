"""TC-41 (AC-16): `make user-reset-password` never exposes the new password."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "infra" / "scripts" / "user_reset_password.sh"
TOKEN = "admin-token-for-tests-1234567890"
PASSWORD = 'p"a\\ss wörd $HOME `x` 123'  # quotes, backslash, unicode, shell chars

FAKE_CURL = """#!/bin/bash
# records how it was called: argv, the body from stdin, and the -H @file contents
printf '%s\\n' "$@" > "$FAKE_DIR/argv"
for ((i = 1; i <= $#; i++)); do
  if [ "${!i}" = "-H" ]; then
    n=$((i + 1)); h="${!n}"
    case "$h" in @*) cat "${h#@}" > "$FAKE_DIR/header" ;; esac
  fi
done
cat > "$FAKE_DIR/stdin"
printf '%s' "${FAKE_STATUS:-204}"
"""


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(0o755)
    fake_dir = tmp_path / "fake"
    fake_dir.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(f"API_PORT=8123\nNEWSDOCK_ADMIN_TOKEN={TOKEN}\n")
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",  # a minimal PATH: the fake curl wins
        "RESET_ROOT": str(project),
        "FAKE_DIR": str(fake_dir),
    }


def run(
    env: dict[str, str], email: str | None, stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    args = ["bash", str(SCRIPT)] + ([email] if email is not None else [])
    return subprocess.run(
        args, env=env, input=stdin, capture_output=True, text=True, check=False
    )


def typed(password: str, confirm: str | None = None) -> str:
    return f"{password}\n{password if confirm is None else confirm}\n"


def fake(env: dict[str, str], name: str) -> str:
    return (Path(env["FAKE_DIR"]) / name).read_text()


def test_the_password_travels_only_in_the_request_body(env: dict[str, str]) -> None:
    result = run(env, "owner@x.io", typed(PASSWORD))
    assert result.returncode == 0, result.stderr
    everything = fake(env, "argv") + result.stdout + result.stderr
    assert PASSWORD not in everything
    assert TOKEN not in everything  # the token goes through a header file too
    assert json.loads(fake(env, "stdin")) == {
        "email": "owner@x.io",
        "password": PASSWORD,
    }
    assert fake(env, "header").strip() == f"Authorization: Bearer {TOKEN}"
    assert "http://127.0.0.1:8123/api/admin/users/reset-password" in fake(env, "argv")
    assert "owner@x.io" in result.stdout and "sessions" in result.stdout


def test_a_mismatched_confirmation_sends_nothing(env: dict[str, str]) -> None:
    result = run(env, "owner@x.io", typed(PASSWORD, "something else entirely"))
    assert result.returncode != 0
    assert "match" in result.stderr.lower()
    assert not (Path(env["FAKE_DIR"]) / "argv").exists()  # curl never ran
    assert PASSWORD not in result.stdout + result.stderr


def test_missing_email_prints_usage(env: dict[str, str]) -> None:
    result = run(env, None)
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()


def test_missing_env_file_or_token_stops_early(env: dict[str, str]) -> None:
    project = Path(env["RESET_ROOT"])
    (project / ".env").write_text("API_PORT=8123\n")
    no_token = run(env, "a@x.io", typed(PASSWORD))
    assert no_token.returncode == 1 and "NEWSDOCK_ADMIN_TOKEN" in no_token.stderr
    (project / ".env").unlink()
    no_env = run(env, "a@x.io", typed(PASSWORD))
    assert no_env.returncode == 1 and ".env" in no_env.stderr
    assert not (Path(env["FAKE_DIR"]) / "argv").exists()


@pytest.mark.parametrize(
    ("status", "needle"),
    [("404", "no such user"), ("422", "rejected"), ("401", "token"), ("403", "token")],
)
def test_error_statuses_fail_with_a_clear_message(
    env: dict[str, str], status: str, needle: str
) -> None:
    result = run({**env, "FAKE_STATUS": status}, "a@x.io", typed(PASSWORD))
    assert result.returncode == 1
    assert needle in result.stderr.lower()
    assert PASSWORD not in result.stdout + result.stderr


def test_make_target_runs_the_script_and_requires_an_email() -> None:
    dry = subprocess.run(
        ["make", "-n", "user-reset-password", "EMAIL=a@x.io"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert dry.returncode == 0
    assert "user_reset_password.sh" in dry.stdout and "a@x.io" in dry.stdout
    bare = subprocess.run(
        ["make", "user-reset-password"],
        cwd=ROOT, capture_output=True, text=True, check=False, input="",
    )  # fmt: skip
    assert bare.returncode != 0 and "usage" in (bare.stdout + bare.stderr).lower()
