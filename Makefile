# newsdock command runner. Plain GNU Make 3.81 syntax only (no .ONESHELL, no $(file ...)).
PYTHON_APPS := ingester processor sink api agent
APPS_DIR ?= apps
WEB := pnpm --dir apps/web
# Compose reads .env when present, else the placeholder .env.example (enough for build, down).
ENV_FILE := $(if $(wildcard .env),.env,.env.example)
COMPOSE := docker compose --env-file $(ENV_FILE) -f infra/compose.yaml

.PHONY: doctor help setup setup-python setup-web test lint-python types-python
.PHONY: imports-python layout-python check-python check-web check test-rules
.PHONY: build up down topics migrate docs-check test-infra test-rules-python

doctor: ## Check the required tools are installed (docker, uv, pnpm, ollama)
	@bash infra/scripts/doctor.sh

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: setup-python setup-web ## Install all dependencies from the lockfiles

setup-python: ## Install the Python workspace (uv sync --all-packages --locked)
	uv sync --all-packages --locked

setup-web: ## Install the web dependencies (pnpm install --frozen-lockfile)
	$(WEB) install --frozen-lockfile

test: ## Run one app's tests: make test APP=<name>
ifeq ($(APP),)
	@echo "usage: make test APP=<name>   (apps: $(PYTHON_APPS) web)" >&2; exit 2
endif
ifeq ($(APP),web)
	@$(WEB) run test
else
	@case " $(PYTHON_APPS) " in \
	  *" $(APP) "*) ;; \
	  *) echo "unknown app '$(APP)' (apps: $(PYTHON_APPS) web)" >&2; exit 2;; \
	esac
	@uv run pytest $(APPS_DIR)/$(APP); rc=$$?; \
	if [ $$rc -eq 5 ]; then echo "no tests ran for '$(APP)' (every app needs at least one test)" >&2; fi; exit $$rc
endif

lint-python: ## ruff lint and format check (includes rule DR-9)
	uv run ruff check .
	uv run ruff format --check .

types-python: ## mypy strict type check
	uv run mypy apps packages infra/scripts infra/migrations

imports-python: ## import-linter contracts (rules DR-6, DR-7)
	uv run lint-imports

layout-python: ## Layout rules DR-1..DR-4 (infra/scripts/check_layout.py)
	uv run python infra/scripts/check_layout.py

check-python: lint-python types-python imports-python layout-python ## All Python checks and tests
	uv run pytest

check-web: ## Web lint, format check, type check and tests
	$(WEB) run lint
	$(WEB) run format:check
	$(WEB) run typecheck
	$(WEB) run test

check: check-python check-web docs-check ## Everything: Python, web and docs checks

test-rules: ## Rule tests: prove each enforced rule fails when violated
	uv run pytest -m rules infra/scripts/tests/rules

test-rules-python: ## Rule tests that need no pnpm (used by the CI check-python job)
	uv run pytest -m "rules and not web" infra/scripts/tests/rules

build: ## Build app images: make build [APP=<name>] (no .env needed)
	$(COMPOSE) --profile apps build $(APP)

test-infra: ## Docker-based tests (images, stack); needs Docker running
	uv run pytest -m docker infra/scripts/tests

up: ## Start Kafka and Postgres, wait until healthy (needs .env)
	@test -f .env || { echo "missing .env: copy .env.example to .env (cp .env.example .env)" >&2; exit 1; }
	$(COMPOSE) up -d --wait kafka postgres
	$(MAKE) topics
	$(MAKE) migrate

down: ## Stop all containers; data volumes are kept
	$(COMPOSE) down

topics: ## Create the Kafka topics (idempotent; starts Kafka if needed)
	$(COMPOSE) run --rm topics

migrate: ## Apply database migrations (alembic upgrade head); Postgres must be up
	$(COMPOSE) run --rm --no-deps migrate

docs-check: ## README sections and relative links (infra/scripts/check_docs.py)
	uv run python infra/scripts/check_docs.py
