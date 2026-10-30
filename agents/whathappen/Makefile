# what-happen agent server. Run from this folder, or from the repo root with
#   make -C agents/whathappen <target>
# Plain GNU Make 3.81 syntax only.
COMPOSE := docker compose

.PHONY: help setup test lint types check once run build up down logs

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

setup: ## Install the dependencies into .venv (uv sync)
	uv sync

test: ## Unit tests
	uv run pytest

lint: ## ruff lint and format check
	uv run ruff check .
	uv run ruff format --check .

types: ## mypy strict
	uv run mypy src tests

check: lint types test ## Everything: lint, types and tests

once: ## One digest cycle on this machine; prints it and writes output/ (needs .env with WHATHAPPEN_API_KEY)
	@test -f .env || { echo "missing .env: cp .env.example .env, then set WHATHAPPEN_API_KEY" >&2; exit 1; }
	uv run python -m whathappen --once

run: ## The hourly loop on this machine (Ctrl-C to stop)
	@test -f .env || { echo "missing .env: cp .env.example .env, then set WHATHAPPEN_API_KEY" >&2; exit 1; }
	uv run python -m whathappen

build: ## Build the image whathappen:dev
	$(COMPOSE) build

up: ## Start the agent server in docker (hourly digests into ./output)
	@test -f .env || { echo "missing .env: cp .env.example .env, then set WHATHAPPEN_API_KEY" >&2; exit 1; }
	@mkdir -p output
	$(COMPOSE) up -d --build

down: ## Stop the agent server
	$(COMPOSE) down

logs: ## Follow the agent server's log
	$(COMPOSE) logs -f whathappen
