#!/usr/bin/env bash
# newsdock preflight: check that the tools a developer must install are present.
# Required on PATH: docker (+ compose, daemon reachable), uv, pnpm, ollama.
# Python 3.12 and Node are NOT required on PATH: uv and pnpm provision them (spec D-5).
# Exit 0 when everything required is present, 1 otherwise (all problems are listed).
# DOCTOR_ROOT overrides the repository root (used by tests).

ROOT="${DOCTOR_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
status=0

hint() {
  case "$1" in
    docker) echo "brew install --cask docker-desktop, then start Docker Desktop" ;;
    uv) echo "brew install uv" ;;
    pnpm) echo "brew install pnpm" ;;
    ollama) echo "brew install --cask ollama-app" ;;
  esac
}

missing() {
  echo "MISSING $1: $2"
  status=1
}

for tool in docker uv pnpm ollama; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing "$tool" "$(hint "$tool")"
  fi
done

have() { command -v "$1" >/dev/null 2>&1; }

if have docker; then
  if ! docker compose version >/dev/null 2>&1; then
    missing "docker compose" "update Docker Desktop (the compose plugin is built in)"
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon not reachable: start Docker Desktop and wait until it is running"
    status=1
  fi
fi

if [ "$status" -ne 0 ]; then
  exit "$status"
fi

echo "docker:   $(docker --version)"
echo "compose:  $(docker compose version)"
echo "uv:       $(uv --version)"
echo "pnpm:     $(pnpm --version)"

python_path="$(uv python find '>=3.12' 2>/dev/null)"
if [ -n "$python_path" ]; then
  echo "python:   $("$python_path" --version 2>&1) (resolved by uv)"
else
  echo "python:   none found by uv; 'make setup' lets uv install 3.12"
fi

package_json="$ROOT/apps/web/package.json"
if [ -f "$package_json" ]; then
  node_version="$(grep -A4 '"runtime"' "$package_json" | grep '"version"' | head -1 | sed 's/.*"version": *"\([^"]*\)".*/\1/')"
  echo "node:     ${node_version:-unpinned} (pinned by pnpm devEngines.runtime; not required on PATH)"
else
  echo "node:     not scaffolded yet (apps/web is created in T-07)"
fi

models="$(ollama list 2>/dev/null | awk 'NR > 1 {print $1}')"
if [ -n "$models" ]; then
  echo "ollama:   models: $(echo "$models" | tr '\n' ' ')"
else
  echo "ollama:   WARNING no model pulled yet (or Ollama is not running); run: ollama pull <model>"
fi
exit 0
