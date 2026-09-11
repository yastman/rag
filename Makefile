.PHONY: help install-dev setup-hooks dev-setup lint format format-check type-check security \
	deps-audit vuln-audit arch-lint complexity docs-coverage audit docs-check \
	check check-frozen candidate-check pre-push fix \
	test test-core test-no-service-lane test-contract test-unit test-unit-full test-unit-extras \
	test-telegram-adapter test-ingestion test-bge-extras test-full test-cov \
	test-smoke test-store-durations demo-gate bot-response-smoke \
	operator-env-exists operator-env-check core-min-up docker-core-up docker-bot-up docker-full-up \
	local-up local-service-health local-up-ingest local-down local-logs local-ps local-build \
	local-redis-recreate release-polling-lock run-bot bot bot-logs-tail bot-logs-errors bot-logs-startup \
	e2e-core-live e2e-core-live-real-llm e2e-telegram-test test-e2e-infra test-e2e-redis-live \
	ingest-unified-preflight ingest-unified-bootstrap ingest-unified \
	qdrant-ensure-indexes demo-bootstrap demo-verify verify-compose-images \
	docker-clean-orphan-worktree-volumes

# Configurable container names & thresholds
REDIS_CONTAINER ?= dev_redis_1
POLLING_LOCK_KEY ?= telegram-bot:polling
RELEASE_POLLING_LOCK_FORCE ?= 0
PROJECT_VERSION := $(shell sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n 1)
LINT_PATHS := src/ telegram_bot/ services/ scripts/

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

ENV_LOAD = if [ -f .env ]; then set -a; . ./.env; set +a; fi;
# Force Linux-native temp dirs in WSL to avoid pytest/capture failures
# when host Windows TEMP/TMP leak into the shell environment.
TMPDIR ?= /tmp
TMP ?= $(TMPDIR)
TEMP ?= $(TMPDIR)
export TMPDIR TMP TEMP
# Python runtime for local pytest targets.
# Pin to 3.12 to match requires-python floor.
# Override: PYTHON_VERSION=3.13 make test-unit
PYTHON_VERSION ?= 3.12
UV_RUN_NO_SYNC ?= uv run --no-sync
PYTEST_PARALLEL_ARGS ?= -n auto --dist=worksteal
PYTEST_FULL_PARALLEL_ARGS ?= -n 2 --dist=worksteal
PYTEST_FULL_PARALLEL_DIRS ?= tests/chaos/ tests/contract/ tests/unit/
PYTEST_FULL_SEQUENTIAL_DIRS ?= tests/e2e/ tests/integration/ tests/load/ tests/smoke/
CORE_LIVE_TEST_PATH := tests/e2e/test_core_live_ingest_answer.py
CORE_LIVE_PYTEST := $(UV_RUN_NO_SYNC) pytest $(CORE_LIVE_TEST_PATH) -v --tb=short -m "e2e and requires_services"
PYTEST_REQUIRES_EXTRAS_IGNORE := $(addprefix --ignore=, \
	tests/unit/test_document_parser.py \
	tests/unit/test_evaluator.py \
	tests/unit/evaluation \
	tests/unit/ingestion \
	tests/unit/observability)
# Explicit owner lanes for tests excluded from the lean broad unit lane.
# Keep these variables in sync with the matching opt-in targets below.
PYTEST_TELEGRAM_ADAPTER_PATHS := \
	tests/unit/dialogs \
	tests/unit/handlers \
	tests/unit/keyboards \
	tests/unit/middlewares \
	tests/unit/pipelines \
	tests/unit/services/test_catalog_rendering.py \
	tests/unit/services/test_catalog_session.py \
	tests/unit/services/test_draft_streamer_removed.py \
	tests/unit/services/test_favorites_service.py
PYTEST_TELEGRAM_ADAPTER_ROOT_TESTS := \
	tests/unit/test_*bot*.py \
	tests/unit/test_bot*.py \
	tests/unit/test_*callback*.py \
	tests/unit/test_*catalog*.py \
	tests/unit/test_*feedback*.py \
	tests/unit/test_*handoff*.py \
	tests/unit/test_*i18n*.py \
	tests/unit/test_*menu*.py \
	tests/unit/test_*preflight*.py \
	tests/unit/test_*middlewares*.py \
	tests/unit/test_card_context.py \
	tests/unit/test_docker_static_validation*.py \
	tests/unit/test_error_handler.py \
	tests/unit/test_feedback.py \
	tests/unit/test_main.py \
	tests/unit/test_perf_fixes.py \
	tests/unit/test_results_pagination_bugs.py \
	tests/unit/test_send_property_card.py
PYTEST_TELEGRAM_ADAPTER_IGNORE_GLOB := $(addprefix --ignore-glob=,$(PYTEST_TELEGRAM_ADAPTER_ROOT_TESTS))
PYTEST_OPTIONAL_ADAPTER_IGNORE := $(addprefix --ignore=,$(PYTEST_TELEGRAM_ADAPTER_PATHS))
PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB := $(PYTEST_TELEGRAM_ADAPTER_IGNORE_GLOB)



help: ## Show this help message
	@echo "$(BLUE)Contextual RAG v$(PROJECT_VERSION) - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@grep -E '^[a-zA-Z0-9_%-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

install-dev: ## Install development dependencies (linters, formatters, etc.)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	uv sync
	@echo "$(GREEN)вњ“ Development dependencies installed$(NC)"

setup-hooks: ## Install pre-commit hooks
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
	@echo "$(GREEN)вњ“ Pre-commit hooks installed$(NC)"

# =============================================================================
# CODE QUALITY CHECKS
# =============================================================================

lint: ## Run Ruff linter (fast)
	@echo "$(BLUE)Running Ruff linter...$(NC)"
	uv run --frozen ruff check $(LINT_PATHS)
	@echo "$(GREEN)вњ“ Ruff check complete$(NC)"

format: ## Format code with Ruff
	@echo "$(BLUE)Formatting code with Ruff...$(NC)"
	uv run ruff format $(LINT_PATHS)
	@echo "$(GREEN)вњ“ Code formatted$(NC)"

format-check: ## Check if code is formatted (read-only: no auto-sync, safe inside candidate-check)
	@echo "$(BLUE)Checking code format...$(NC)"
	@$(UV_RUN_NO_SYNC) ruff format $(LINT_PATHS) --check
	@echo "$(GREEN)вњ“ Format check complete$(NC)"

type-check: ## Run MyPy type checking
	@echo "$(BLUE)Running MyPy type checking...$(NC)"
	uv run --frozen mypy $(LINT_PATHS) --ignore-missing-imports --no-error-summary
	@echo "$(GREEN)вњ“ Type check complete$(NC)"

security: ## Run Bandit security scan + Vulture dead-code check
	@echo "$(BLUE)Running Bandit security checks...$(NC)"
	uv run bandit -r $(LINT_PATHS) -c pyproject.toml
	@echo "$(GREEN)вњ“ Bandit security check complete$(NC)"
	@echo "$(BLUE)Checking for dead code with Vulture...$(NC)"
	uv run vulture $(LINT_PATHS) vulture_whitelist.py --min-confidence 80 --exclude "*site-packages*,*dist-info*,__pycache__,.pytest_cache,.ruff_cache,.mypy_cache,*.egg-info,.venv*"
	@echo "$(GREEN)вњ“ Vulture dead-code check complete$(NC)"

deps-audit: ## Check for unused/missing/misplaced deps with deptry
	@echo "$(BLUE)Running deptry dependency audit...$(NC)"
	uv run --frozen deptry .
	@echo "$(GREEN)вњ“ deptry complete$(NC)"

vuln-audit: ## Audit installed packages in .venv for known CVEs with pip-audit
	@echo "$(BLUE)Running pip-audit vulnerability scan...$(NC)"
	uv run --frozen pip-audit --path .venv
	@echo "$(GREEN)вњ“ pip-audit complete$(NC)"

arch-lint: ## Enforce module boundary contracts with import-linter
	@echo "$(BLUE)Running import-linter architecture checks...$(NC)"
	uv run --frozen lint-imports
	@echo "$(GREEN)вњ“ import-linter complete$(NC)"

complexity: ## Report cyclomatic complexity hotspots (C or worse) with radon
	@echo "$(BLUE)Cyclomatic complexity (grade C+)...$(NC)"
	uv run --frozen radon cc src telegram_bot -s -n C
	@echo "$(BLUE)Maintainability index...$(NC)"
	uv run --frozen radon mi src telegram_bot -s
	@echo "$(GREEN)вњ“ radon complete$(NC)"

docs-coverage: ## Check docstring coverage on stable public layers (в‰Ґ70%)
	@echo "$(BLUE)Checking docstring coverage...$(NC)"
	uv run --frozen interrogate src/core src/runtime src/ingestion/unified -v --fail-under 70
	@echo "$(GREEN)вњ“ interrogate complete$(NC)"

audit: lint type-check security deps-audit vuln-audit arch-lint complexity ## Full quality + security + architecture audit
	@echo "$(GREEN)вњ“вњ“вњ“ Full audit complete вњ“вњ“вњ“$(NC)"

# =============================================================================
# TESTING
# =============================================================================

test: ## Run deterministic core PR/local gate (core + no-service integration/smoke lane)
	@echo "$(BLUE)Running deterministic core gate (test-core + no-service integration/smoke lane)...$(NC)"
	$(MAKE) test-core
	$(MAKE) test-no-service-lane
	@echo "$(GREEN)вњ“ Deterministic core gate complete$(NC)"

test-no-service-lane: ## Run no-service integration/smoke lane (#2324 Phase 1.2)
	@echo "$(BLUE)Running no-service integration/smoke lane (-m no_services)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/integration tests/smoke -q --timeout=30 -m "no_services and not requires_extras and not slow"
	@echo "$(GREEN)вњ“ No-service integration/smoke lane complete$(NC)"

test-core: ## Run monolith core-required tests only (local/manual)
	@echo "$(BLUE)Running monolith core test gate...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest \
	  tests/unit/core/ \
	  tests/unit/runtime/ \
	  tests/regression/ \
	  tests/characterization/ \
	  tests/contract/test_runtime_no_telegram_bot_coupling_contract.py \
	  tests/contract/test_layering_no_telegram_bot_imports_contract.py \
	  --ignore=tests/unit/core/test_pipeline.py \
	  -q --timeout=30 -m "not requires_extras and not slow"
	@echo "$(GREEN)вњ“ Monolith core test gate complete$(NC)"

test-telegram-adapter: ## Run Telegram adapter unit tests explicitly
	@echo "$(BLUE)Running Telegram adapter tests...$(NC)"
	uv sync --extra telegram --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_TELEGRAM_ADAPTER_PATHS) $(PYTEST_TELEGRAM_ADAPTER_ROOT_TESTS) -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)вњ“ Telegram adapter tests complete$(NC)"

test-ingestion: ## Run ingestion tests (Markdown-only pipeline, #3235 вЂ” no extras needed)
	@echo "$(BLUE)Running ingestion tests...$(NC)"
	uv sync --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ingestion/ -q --timeout=30
	@echo "$(GREEN)вњ“ Ingestion tests complete$(NC)"

# bge-m3-api FastAPI endpoint tests вЂ” require fastapi (bge-extras).
# These are silently skipped by importorskip in the core/unit gates (fastapi absent).
# Run this lane explicitly after: make docker-core-up  (sidecars not required).
test-bge-extras: ## Run BGE-M3 FastAPI endpoint tests (bge-extras extra вЂ” installs fastapi)
	@echo "$(BLUE)Running bge-m3-api endpoint tests (bge-extras)...$(NC)"
	uv sync --extra bge-extras --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest \
	  tests/unit/test_bge_m3_endpoints.py \
	  tests/unit/test_bge_m3_rerank.py \
	  -q --timeout=30 -m "not slow and not requires_services"
	@echo "$(GREEN)вњ“ BGE-extras tests complete$(NC)"

test-full: ## Run full test suite with hybrid parallelism (all tiers)
	@echo "$(BLUE)Running full test suite...$(NC)"
	uv sync --all-extras --all-groups
	@echo "$(BLUE)Phase 1/2: parallel-safe suites...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_FULL_PARALLEL_DIRS) $(PYTEST_FULL_PARALLEL_ARGS) --timeout=30 $(PYTEST_ADDOPTS)
	@echo "$(BLUE)Phase 2/2: stateful/live suites sequentially...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_FULL_SEQUENTIAL_DIRS) --timeout=30 $(PYTEST_ADDOPTS)
	@echo "$(GREEN)вњ“ Full test suite complete$(NC)"

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	PYTHONPATH=scripts/covfix uv run pytest tests/ --cov=src --cov=telegram_bot --cov-report=html --cov-report=term
	@echo "$(GREEN)вњ“ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ## Run broad unit test lane locally in parallel
	@echo "$(BLUE)Running broad unit tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB) $(PYTEST_PARALLEL_ARGS) -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)вњ“ Broad unit tests complete$(NC)"

test-unit-full: ## Run all unit tests including optional-dep tests (nightly/main)
	@echo "$(BLUE)Running full unit tests (all extras)...$(NC)"
	uv sync --all-extras --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)вњ“ Full unit tests complete$(NC)"

test-unit-extras: ## Run optional-extra unit tests only
	@echo "$(BLUE)Running optional-extra unit tests...$(NC)"
	uv sync --all-extras --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "requires_extras"
	@echo "$(GREEN)вњ“ Optional-extra unit tests complete$(NC)"

test-contract: ## Run static contract tests (no Docker; optional SDK lanes excluded by markers)
	@echo "$(BLUE)Running static contract tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) pytest tests/contract/ $(PYTEST_PARALLEL_ARGS) -q --timeout=30 -m "not requires_extras"
	@echo "$(GREEN)вњ“ Static contract tests complete$(NC)"

test-store-durations: ## Update .test_durations for pytest-split CI sharding
	@echo "$(BLUE)Generating test duration data...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) --store-durations $(PYTEST_PARALLEL_ARGS) --timeout=30 -m "not legacy_api and not requires_extras and not slow" -q
	@echo "$(GREEN)вњ“ .test_durations updated вЂ” commit this file$(NC)"

# =============================================================================
# SMOKE & LOAD TESTS
# =============================================================================

# MODE="" runs the full gate (readiness + real Telegram journey);
# MODE="--prerequisites-only" runs the readiness snapshot only.
MODE ?=

demo-gate: ## Run the automated five-minute real-estate Telegram demo gate (#3205)
	@echo "$(BLUE)Running demo gate (#3205) $(MODE)...$(NC)"
	$(ENV_LOAD) uv run --group e2e --python $(PYTHON_VERSION) python -m scripts.e2e.demo_gate $(MODE)
	@echo "$(GREEN)вњ“ Demo gate complete$(NC)"

test-smoke: ## Run smoke tests (requires live services)
	@echo "$(BLUE)Running smoke tests...$(NC)"
	uv run pytest tests/smoke/ -v --tb=short
	@echo "$(GREEN)вњ“ Smoke tests complete$(NC)"

# =============================================================================
# REDIS VERIFICATION
# =============================================================================

BOT_RESPONSE_SMOKE_FLAGS ?=

bot-response-smoke: operator-env-exists ## End-to-end gate: prove `make bot` actually answers a Telegram message (#2192)
	@echo "$(BLUE)Running bot response smoke gate...$(NC)"
	@uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python -m scripts.probe.bot_response_smoke $(BOT_RESPONSE_SMOKE_FLAGS)
	@echo "$(GREEN)вњ“ Bot response smoke gate passed$(NC)"

# =============================================================================
# CLEANUP
# =============================================================================

docker-clean-orphan-worktree-volumes: ## Report Docker volumes from removed git worktrees (dry-run, see #1546)
	@bash scripts/cleanup_orphaned_worktree_volumes.sh

# =============================================================================
# DOCKER PROFILES
# =============================================================================

# Compose command вЂ” no --compatibility (Docker Compose v5 rejects it)
COMPOSE_CMD := docker compose
CORE_MIN_COMPOSE_FILE := -f compose.core.yml
# Operator env (#3367): real build/up commands require an explicit operator env
# file. When .env is absent they FAIL with an actionable message вЂ” they never
# fall back to the CI Compose fixture (dummy credentials + an invalid BGE
# context). That fixture is confined to named CI/static-validation targets
# (pytest lanes, .github/workflows/ci.yml compose-config).
OPERATOR_ENV ?= .env
# Bounded compose waits (#3361): bge-m3 declares a 420s cold-load start
# period, so the full-stack bound must exceed start_period + healthcheck
# retries (~420s + 3x30s). Override per run, e.g.
#   make docker-full-up FULL_UP_WAIT_TIMEOUT=900
FULL_UP_WAIT_TIMEOUT ?= 600
CORE_UP_WAIT_TIMEOUT ?= 300
# Local dev: explicit -f flags instead of colon COMPOSE_FILE
LOCAL_COMPOSE_CMD := docker compose -f compose.yml -f compose.dev.yml --env-file $(OPERATOR_ENV)
# Runtime env for native-run bot commands and E2E trace gates: the same
# explicit operator env (worktrees may override it, e.g. to the main checkout).
RAG_RUNTIME_ENV_FILE ?= $(OPERATOR_ENV)
export RAG_RUNTIME_ENV_FILE

operator-env-exists: ## Fail with an actionable message when the operator env file is missing
	@if [ ! -f "$(OPERATOR_ENV)" ]; then \
		echo "$(RED)ERROR: operator env file '$(OPERATOR_ENV)' not found.$(NC)"; \
		echo "  Real commands never fall back to the CI Compose fixture (#3367)."; \
		echo "  Fix: cp .env.example $(OPERATOR_ENV), fill in the required values,"; \
		echo "  then re-run (or pass OPERATOR_ENV=/path/to/env)."; \
		exit 1; \
	fi

operator-env-check: operator-env-exists ## Validate operator env before Compose: secrets shape, native paths, BGE artifact pin (#3367)
	@echo "$(BLUE)Validating operator env ($(OPERATOR_ENV))...$(NC)"
	@$(UV_RUN_NO_SYNC) python scripts/validate_operator_env.py --env-file "$(OPERATOR_ENV)"
	@echo "$(GREEN)вњ“ Operator env valid$(NC)"

.PHONY: core-min-up docker-core-up docker-bot-up docker-full-up

core-min-up: ## Start minimal core services only (qdrant + redis)
	@echo "$(BLUE)Starting minimal core services (qdrant + redis)...$(NC)"
	docker compose $(CORE_MIN_COMPOSE_FILE) up -d
	@echo "$(GREEN)вњ“ Minimal core services started$(NC)"

docker-core-up: operator-env-check ## Start default local compose stack (unprofiled services; env-validated #3367)
	@echo "$(BLUE)Starting core services (bounded wait: $(CORE_UP_WAIT_TIMEOUT)s, #3361)...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d --wait --wait-timeout $(CORE_UP_WAIT_TIMEOUT)
	@echo "$(GREEN)вњ“ Core services started$(NC)"

docker-bot-up: operator-env-check ## Start core + bot services (bot; env-validated #3367)
	@echo "$(BLUE)Starting bot services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile bot up -d
	@echo "$(GREEN)вњ“ Bot services started$(NC)"

docker-full-up: operator-env-check ## Start all services and wait: exit 0 only when all six are healthy; honest failure names them (full stack #3361)
	@echo "$(BLUE)Starting full stack (bounded wait: $(FULL_UP_WAIT_TIMEOUT)s)...$(NC)"
	@if $(LOCAL_COMPOSE_CMD) --profile full up -d --wait --wait-timeout $(FULL_UP_WAIT_TIMEOUT); then \
		echo "$(GREEN)вњ“ Full stack started: 6/6 services healthy (postgres redis qdrant bge-m3 bot ingestion)$(NC)"; \
	else \
		status=$$?; \
		echo "$(RED)вњ— Full stack failed to become healthy (exit $$status). Container statuses:$(NC)" >&2; \
		$(LOCAL_COMPOSE_CMD) --profile full ps -a >&2 || true; \
		echo "$(YELLOW)  Above: service names and statuses only вЂ” secrets are never printed.$(NC)" >&2; \
		echo "$(YELLOW)  Diagnose the named service: docker compose logs <service> (or make local-logs).$(NC)" >&2; \
		exit $$status; \
	fi

# =============================================================================
# DEVELOPMENT WORKFLOW
# =============================================================================

dev-setup: install-dev setup-hooks docker-core-up ## Complete development setup
	@echo "$(GREEN)вњ“вњ“вњ“ Development environment ready! вњ“вњ“вњ“$(NC)"
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Copy .env.example to .env"
	@echo "  2. Fill in your API keys"
	@echo "  3. Run 'make test' to verify setup"

# =============================================================================
# DOCUMENTATION
# =============================================================================

docs-check: ## Check Markdown relative links for broken targets
	@echo "$(BLUE)Checking documentation links...$(NC)"
	python3 scripts/check_markdown_links.py
	@echo "$(GREEN)вњ“ Documentation links OK$(NC)"

# =============================================================================
# QUICK COMMANDS
# =============================================================================

check: lint type-check ## Quick check (lint + types)
	@echo "$(GREEN)вњ“ Quick check complete$(NC)"

check-frozen: ## Read-only check: fail if .venv is stale, then lint + type-check without uv sync
	@echo "$(BLUE)Checking frozen uv environment...$(NC)"
	@uv sync --frozen --check || { \
		echo "$(RED)Environment is stale. Run 'uv sync --frozen' in an isolated worktree .venv, then retry.$(NC)"; \
		exit 1; \
	}
	@echo "$(BLUE)Running Ruff lint without uv auto-sync...$(NC)"
	@$(UV_RUN_NO_SYNC) ruff check $(LINT_PATHS)
	@echo "$(GREEN)вњ“ Ruff check complete$(NC)"
	@echo "$(BLUE)Running MyPy type-check without uv auto-sync...$(NC)"
	@$(UV_RUN_NO_SYNC) mypy $(LINT_PATHS) --ignore-missing-imports --no-error-summary
	@echo "$(GREEN)вњ“ Frozen check complete$(NC)"

candidate-check: check-frozen format-check test test-contract ## Authoritative local delivery gate (format parity with CI before long lanes, #3326)

pre-push: lint format-check test-core ## Pre-push gate (lint + format-check + core tests)
	@echo "$(GREEN)вњ“ Pre-push gate passed$(NC)"

fix: ## Fix all auto-fixable issues (Ruff auto-fix + format)
	uv run ruff check $(LINT_PATHS) --fix
	uv run ruff format $(LINT_PATHS)
	@echo "$(GREEN)вњ“ Auto-fixes applied$(NC)"

# =============================================================================
# Local Development (compose.yml + compose.dev.yml via explicit -f flags)
# =============================================================================


.PHONY: local-up local-up-ingest local-down local-logs local-ps local-build local-redis-recreate release-polling-lock run-bot bot
# Core demo sidecars (#3241): PostgreSQL is NOT part of the core demo topology вЂ”
# bookmarks/user features are an optional capability. Opt in explicitly with
# `$(LOCAL_COMPOSE_CMD) --profile postgres up -d` or `make docker-full-up`.
LOCAL_SERVICES := redis qdrant bge-m3

LOCAL_INGEST_SERVICES := ingestion
LOCAL_ALL_SERVICES := $(LOCAL_SERVICES) $(LOCAL_INGEST_SERVICES)

local-up: operator-env-check  ## Start local Docker services (env-validated #3367; bot runs via make run-bot; PostgreSQL opt-in: --profile postgres)
	$(LOCAL_COMPOSE_CMD) up -d $(LOCAL_SERVICES)
	@echo "$(GREEN)вњ“ Local services started. Run bot: make run-bot$(NC)"

local-service-health: ## Check health of local services: Qdrant, Redis, BGE-M3, Ingestion
	@bash scripts/check_services.sh
local-up-ingest: operator-env-check  ## Start local services + ingestion (env-validated #3367) for ingestion workflows
	$(LOCAL_COMPOSE_CMD) --profile ingest up -d $(LOCAL_ALL_SERVICES)
	@echo "$(GREEN)вњ“ Local services + ingestion started$(NC)"

release-polling-lock:  ## Delete the local Redis Telegram polling lock after confirming no bot is alive
	@$(ENV_LOAD) \
	container="$${REDIS_CONTAINER:-$(REDIS_CONTAINER)}"; \
	key="$${POLLING_LOCK_KEY:-$(POLLING_LOCK_KEY)}"; \
	force="$${RELEASE_POLLING_LOCK_FORCE:-$(RELEASE_POLLING_LOCK_FORCE)}"; \
	if [ "$$force" != "1" ] && [ "$$force" != "true" ]; then \
		running_bot_containers="$$(docker ps --filter name=bot --format '{{.Names}}' | tr '\n' ' ')"; \
		if [ -n "$$running_bot_containers" ]; then \
			echo "$(RED)Refusing to release polling lock while bot container(s) are running: $$running_bot_containers$(NC)"; \
			echo "$(YELLOW)Stop the bot first, or set RELEASE_POLLING_LOCK_FORCE=1 for an emergency override.$(NC)"; \
			exit 1; \
		fi; \
		native_bot_pids="$$(if command -v pgrep >/dev/null 2>&1; then pgrep -f 'python.*-m telegram_bot[.]main' || true; fi)"; \
		if [ -n "$$native_bot_pids" ]; then \
			echo "$(RED)Refusing to release polling lock while native bot process(es) are running: $$native_bot_pids$(NC)"; \
			echo "$(YELLOW)Stop make run-bot first, or set RELEASE_POLLING_LOCK_FORCE=1 for an emergency override.$(NC)"; \
			exit 1; \
		fi; \
	fi; \
	if ! docker inspect "$$container" >/dev/null 2>&1; then \
		container="$$(docker ps --filter name=redis -q | head -1)"; \
	fi; \
	if [ -z "$$container" ]; then \
		echo "$(RED)No Redis container found. Start services with 'make local-up' first.$(NC)"; \
		exit 1; \
	fi; \
	redis_exec() { \
		if [ -n "$${REDIS_PASSWORD:-}" ]; then \
			docker exec -e REDISCLI_AUTH="$$REDIS_PASSWORD" "$$container" redis-cli "$$@"; \
		else \
			docker exec "$$container" redis-cli "$$@"; \
		fi; \
	}; \
	owner="$$(redis_exec GET "$$key")"; \
	pttl="$$(redis_exec PTTL "$$key")"; \
	if [ -z "$$owner" ]; then \
		echo "$(GREEN)Polling lock '$$key' is already free in Redis container '$$container'.$(NC)"; \
		exit 0; \
	fi; \
	echo "$(YELLOW)Deleting polling lock '$$key' from Redis container '$$container'.$(NC)"; \
	echo "$(YELLOW)Owner: $$owner$(NC)"; \
	echo "$(YELLOW)PTTL ms: $$pttl$(NC)"; \
	redis_exec DEL "$$key" >/dev/null; \
	echo "$(GREEN)вњ“ Polling lock released. Run 'make run-bot' again.$(NC)"

run-bot: operator-env-exists  ## Run bot locally with the explicit operator env (requires: make local-up)
	$(UV_RUN_NO_SYNC) --env-file "$$RAG_RUNTIME_ENV_FILE" python -m telegram_bot.main

bot: operator-env-exists ## Alias: run bot (tee output to logs/bot-run.log)
	@mkdir -p logs
	@bash -o pipefail -c '$(UV_RUN_NO_SYNC) --env-file "$$RAG_RUNTIME_ENV_FILE" python -m telegram_bot.main 2>&1 | tee logs/bot-run.log'; \
	status=$$?; echo '[COMPLETE]'; exit $$status

# =============================================================================
# BOT LOG TRIAGE (issue #1418)
# Operator workflow:
#   make bot                  # produce logs/bot-run.log
#   make bot-logs-tail        # follow live log
#   make bot-logs-errors      # show ERROR/CRITICAL lines + tracebacks
#   make bot-logs-startup     # show preflight + Startup verdict events
# =============================================================================

.PHONY: bot-logs-tail bot-logs-errors bot-logs-startup

bot-logs-tail:  ## Follow logs/bot-run.log (live stream of bot output)
	@if [ ! -f logs/bot-run.log ]; then \
		echo "$(YELLOW)logs/bot-run.log not found вЂ” run \`make bot\` first$(NC)"; \
		exit 1; \
	fi
	@tail -F logs/bot-run.log

bot-logs-errors:  ## Show recent ERROR/CRITICAL lines and Tracebacks from logs/bot-run.log
	@if [ ! -f logs/bot-run.log ]; then \
		echo "$(YELLOW)logs/bot-run.log not found вЂ” run \`make bot\` first$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Recent errors in logs/bot-run.log:$(NC)"
	@grep -nE 'ERROR|CRITICAL|Traceback|exception' logs/bot-run.log | tail -n $${BOT_LOG_LINES:-200} || \
		echo "$(GREEN)No error/critical lines found$(NC)"

bot-logs-startup:  ## Show recent startup/preflight events from logs/bot-run.log
	@if [ ! -f logs/bot-run.log ]; then \
		echo "$(YELLOW)logs/bot-run.log not found вЂ” run \`make bot\` first$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Recent startup events in logs/bot-run.log:$(NC)"
	@grep -nE 'Startup verdict|Preflight|Logging configured' logs/bot-run.log | tail -n $${BOT_LOG_LINES:-100} || \
		echo "$(YELLOW)No startup events found$(NC)"

local-down:  ## Stop local Docker services
	$(LOCAL_COMPOSE_CMD) stop $(LOCAL_ALL_SERVICES) || true
	$(LOCAL_COMPOSE_CMD) rm -f $(LOCAL_ALL_SERVICES) || true

local-logs:  ## View local Docker logs
	$(LOCAL_COMPOSE_CMD) logs -f $(LOCAL_ALL_SERVICES)

local-ps:  ## Show local Docker status
	$(LOCAL_COMPOSE_CMD) ps $(LOCAL_ALL_SERVICES)

local-build: operator-env-check  ## Rebuild local Docker services (env-validated before build #3367)
	$(LOCAL_COMPOSE_CMD) build bge-m3 ingestion

local-redis-recreate:  ## Recreate local Redis container after REDIS_PASSWORD/.env changes
	@echo "$(BLUE)Recreating local Redis container with current .env values...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d --no-deps --force-recreate redis
	@echo "$(GREEN)вњ“ Local Redis recreated. Next: make local-service-health$(NC)"

# =============================================================================
# E2E TESTING
# =============================================================================

.PHONY: e2e-core-live e2e-core-live-real-llm e2e-telegram-test test-e2e-infra test-e2e-redis-live

e2e-core-live: ## Run simplification core live golden path (Qdrant + BGE-M3)
	@echo "$(BLUE)Running simplification core live E2E golden path...$(NC)"
	E2E_CORE_STRICT=1 $(CORE_LIVE_PYTEST)
	@echo "$(GREEN)вњ“ Simplification core live E2E complete$(NC)"

e2e-core-live-real-llm: ## Run simplification core live golden path with real LLM provider
	@echo "$(BLUE)Running simplification core live E2E with real LLM...$(NC)"
	@$(ENV_LOAD) \
	missing=""; \
	if [ -z "$$LLM_MODEL" ]; then missing="$$missing LLM_MODEL"; fi; \
	if [ -z "$$LLM_API_KEY$$OPENAI_API_KEY" ]; then missing="$$missing (LLM_API_KEY|OPENAI_API_KEY)"; fi; \
	if [ -n "$$missing" ]; then \
		echo "$(RED)Missing required real LLM env:$$missing$(NC)"; \
		exit 1; \
	fi; \
	E2E_CORE_STRICT=1 E2E_CORE_REAL_LLM=1 $(CORE_LIVE_PYTEST)
	@echo "$(GREEN)вњ“ Simplification core live real LLM E2E complete$(NC)"

e2e-telegram-test: operator-env-exists ## Run Telegram userbot E2E runner (Telethon + judge; explicit operator env #3367)
	@echo "$(BLUE)Running Telegram E2E runner...$(NC)"
	uv run --group e2e --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py
	@echo "$(GREEN)вњ“ Telegram E2E runner complete$(NC)"

test-e2e-infra: ## Run live infrastructure E2E: ingestion + Redis + Qdrant (#2771, #3235)
	$(UV_RUN_NO_SYNC) pytest tests/e2e/test_infra_ingestion_redis_qdrant.py -v --tb=short -m "e2e and requires_services"
	@echo "$(GREEN)вњ“ Infra E2E complete$(NC)"

# Strict lane (#3368): each test starts its own disposable authenticated Redis
# container (Docker required); a missing daemon FAILS instead of skipping.
# Environment: uv sync --frozen --extra telegram --extra redis
test-e2e-redis-live: ## Run live Redis mode + two-owner polling-lock E2E (#3368; Docker, redis extra)
	E2E_REDIS_STRICT=1 $(UV_RUN_NO_SYNC) pytest tests/e2e/test_redis_modes_live.py -v --tb=short -m "e2e and requires_services"
	@echo "$(GREEN)вњ“ Redis modes + polling-lock live E2E complete$(NC)"

# =============================================================================
# CANONICAL HERMETIC LIVE HARNESS (#3414)
# =============================================================================
# One run id + one isolated Compose project per invocation; UUID Qdrant
# collection, Redis prefix/db and PostgreSQL schema per xdist worker; real
# local Redis/Qdrant/PostgreSQL/BGE with deterministic provider adapters;
# required mode has ZERO service-related skips; teardown removes only the
# exact run-owned resources. The old core lane (`make e2e-core-live`) stays
# read-only until cutover; its consumer drifted from the core API at the
# base commit, so it is not part of this default lane (successor #3413).

E2E_RUN_ID ?= $(shell python -c "import uuid; print(uuid.uuid4().hex[:12])")
E2E_HARNESS_STACK_WAIT ?= 900
E2E_HARNESS_PYTEST_ARGS ?= -n 2 --dist=worksteal
E2E_HARNESS_PATHS ?= tests/e2e_core/test_live_stack_required_live.py
# Optional extra compose -f file for hosts where the default loopback ports
# (5432/6333/6379/8000) are occupied; use `!override` port lists there and
# pass the matching endpoints via env (QDRANT_URL, BGE_M3_URL, REDIS_URL,
# POSTGRES_DSN) to the pytest step.
E2E_HARNESS_EXTRA_COMPOSE ?=
# -p names the project AND the built image (rag-e2e-<run-id>_bge-m3); the
# teardown removes exactly those run-owned resources.
E2E_HARNESS_COMPOSE := docker compose -p rag-e2e-$(E2E_RUN_ID) -f compose.yml -f compose.dev.yml $(E2E_HARNESS_EXTRA_COMPOSE) --env-file $(OPERATOR_ENV)

.PHONY: e2e-harness e2e-harness-down

e2e-harness: operator-env-check ## Canonical hermetic live E2E harness: run-owned compose stack + required no-skip lane (#3414)
	@echo "$(BLUE)Harness run rag-e2e-$(E2E_RUN_ID): isolated compose project + required lane (zero service skips)$(NC)"
	@set -e; \
	$(E2E_HARNESS_COMPOSE) --profile postgres up -d --wait --wait-timeout $(E2E_HARNESS_STACK_WAIT) postgres redis qdrant bge-m3; \
	status=0; \
	set -a; . $(OPERATOR_ENV); set +a; \
	PYTHON_DOTENV_DISABLED=1 E2E_RUN_ID=$(E2E_RUN_ID) E2E_HARNESS_REQUIRED=1 \
		$(UV_RUN_NO_SYNC) pytest $(E2E_HARNESS_PATHS) -v --tb=short -m "e2e and requires_services" $(E2E_HARNESS_PYTEST_ARGS) || status=$$?; \
	$(E2E_HARNESS_COMPOSE) --profile postgres down -v --remove-orphans >/dev/null 2>&1 || true; \
	docker image rm -f rag-e2e-$(E2E_RUN_ID)_bge-m3 >/dev/null 2>&1 || true; \
	if [ $$status -ne 0 ]; then \
		echo "$(RED)вњ— Harness lane failed (exit $$status); project rag-e2e-$(E2E_RUN_ID) removed$(NC)" >&2; \
		exit $$status; \
	fi; \
	echo "$(GREEN)вњ“ Hermetic harness run rag-e2e-$(E2E_RUN_ID) complete: stack down, volumes removed$(NC)"

e2e-harness-down: ## Remove a leftover harness compose project (make e2e-harness-down E2E_RUN_ID=<id>)
	@echo "$(BLUE)Removing harness project rag-e2e-$(E2E_RUN_ID)...$(NC)"
	@$(E2E_HARNESS_COMPOSE) --profile postgres down -v --remove-orphans
	@docker image rm -f rag-e2e-$(E2E_RUN_ID)_bge-m3 >/dev/null 2>&1 || true
	@echo "$(GREEN)вњ“ Harness project rag-e2e-$(E2E_RUN_ID) removed$(NC)"

# DOCUMENT INGESTION (Ingestion Pipeline)
# =============================================================================

.PHONY: ingest-unified-preflight ingest-unified-bootstrap ingest-unified

ingest-unified-preflight: ## Check unified ingestion dependencies and source path
	@echo "$(BLUE)Running unified ingestion preflight...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli preflight

ingest-unified-bootstrap: ## Create/validate unified ingestion collection schema
	@echo "$(BLUE)Bootstrapping unified ingestion collection...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli bootstrap --require-colbert

ingest-unified: ## Run unified ingestion once
	@echo "$(BLUE)Running unified ingestion...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli run
	@echo "$(GREEN)вњ“ Ingestion complete$(NC)"

# =============================================================================
# QDRANT BACKUP
# =============================================================================

.PHONY: qdrant-ensure-indexes demo-bootstrap demo-verify

qdrant-ensure-indexes: ## Ensure contract payload indexes for BOTH product collections (non-destructive, #3202)
	@echo "$(BLUE)Ensuring Qdrant payload indexes (knowledge + apartments)...$(NC)"
	@$(ENV_LOAD) uv run python -m scripts.qdrant_ensure_indexes
	@echo "$(GREEN)вњ“ Qdrant payload indexes ensured$(NC)"

demo-bootstrap: ## Idempotent demo setup/ingest/verify for both Qdrant collections (#3202)
	@echo "$(BLUE)Bootstrapping demo data for both Qdrant collections...$(NC)"
	@$(ENV_LOAD) uv run python -m scripts.demo_bootstrap
	@echo "$(GREEN)вњ“ Demo bootstrap complete$(NC)"

demo-verify: ## Read-only readiness gate for both Qdrant collections (#3202)
	@echo "$(BLUE)Verifying Qdrant demo readiness (read-only)...$(NC)"
	@$(ENV_LOAD) uv run python -m scripts.demo_bootstrap --verify-only
	@echo "$(GREEN)вњ“ Demo readiness verified$(NC)"

# =============================================================================
# DOCKER IMAGE DRIFT (#322)
# =============================================================================

.PHONY: verify-compose-images docker-clean-orphan-worktree-volumes

verify-compose-images: ## Check running containers match compose-pinned images and published ports
	@python3 scripts/check_image_drift.py -f compose.yml -f compose.dev.yml --fix
