.PHONY: help install install-dev install-all lint format type-check security compile-python test test-full test-cov clean all-checks \
	test-preflight test-smoke test-load-eviction \
	test-telegram-adapter test-providers-extra test-ingest-extra \
	smoke-fast smoke-zoo \
	ingest-dir ingest-status ingest-services \
	ingest-unified-preflight ingest-unified-bootstrap ingest-unified ingest-unified-watch ingest-unified-status ingest-unified-reprocess ingest-unified-logs \
	lock update update-pkg reinstall setup-hooks \
	qdrant-backup qdrant-cleanup \
	git-hygiene git-hygiene-fix pr-hygiene issue-hygiene repo-cleanup repo-cleanup-force \
	docker-clean docker-clean-aggressive
	test-contract \
	preflight-bot \
	preflight-qdrant \
	release-polling-lock \
	docs-check \
	remote-docker-status remote-compose-config remote-docker-ps remote-env-sync remote-env-check \
	remote-core-up remote-core-ps remote-core-logs remote-core-health remote-core-env-check \
	remote-bot-up remote-bot-restart remote-bot-logs \
	remote-local-up remote-local-down remote-local-logs remote-service-health

# Configurable container names & thresholds
REDIS_CONTAINER ?= dev_redis_1
POLLING_LOCK_KEY ?= telegram-bot:polling
RELEASE_POLLING_LOCK_FORCE ?= 0
EXPECTED_MAXMEMORY_SAMPLES ?= 10
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
	tests/unit/test_ragas_evaluation.py \
	tests/unit/api \
	tests/unit/evaluation \
	tests/unit/ingestion \
	tests/unit/observability)
# Explicit owner lanes for tests excluded from the lean broad unit lane.
# Keep these variables in sync with the matching opt-in targets below.
PYTEST_TELEGRAM_ADAPTER_PATHS := \
	tests/unit/agents \
	tests/unit/dialogs \
	tests/unit/handlers \
	tests/unit/keyboards \
	tests/unit/middlewares \
	tests/unit/pipelines \
	tests/unit/services/test_catalog_rendering.py \
	tests/unit/services/test_catalog_session.py \
	tests/unit/services/test_draft_streamer_removed.py \
	tests/unit/services/test_favorites_service.py \
	tests/unit/services/test_kommo_models.py
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
	tests/unit/test_agent_streaming.py \
	tests/unit/test_card_context.py \
	tests/unit/test_cmd_call.py \
	tests/unit/test_docker_static_validation*.py \
	tests/unit/test_error_handler.py \
	tests/unit/test_feedback.py \
	tests/unit/test_kommo_token_seed.py \
	tests/unit/test_main.py \
	tests/unit/test_perf_fixes.py \
	tests/unit/test_results_pagination_bugs.py \
	tests/unit/test_send_property_card.py \
	tests/unit/test_thread_routing.py \
	tests/unit/test_topic_service_init.py
PYTEST_TELEGRAM_ADAPTER_IGNORE_GLOB := $(addprefix --ignore-glob=,$(PYTEST_TELEGRAM_ADAPTER_ROOT_TESTS))
PYTEST_PROVIDER_CONTEXTUALIZATION_PATHS := \
	tests/unit/contextualization \
	tests/unit/test_claude_contextualizer.py \
	tests/unit/test_contextualization_batch.py
# Temporary #2526 partition only: these legacy graph/langgraph tests are owned
# by the explicit lane below until the #2495 graph/API rewrite retargets them.
PYTEST_LEGACY_GRAPH_PATHS := \
	tests/unit/graph \
	tests/unit/integrations \
	tests/unit/test_latency_units.py
PYTEST_OPTIONAL_ADAPTER_IGNORE := $(addprefix --ignore=,$(PYTEST_TELEGRAM_ADAPTER_PATHS))
PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB := $(PYTEST_TELEGRAM_ADAPTER_IGNORE_GLOB)
PYTEST_OPTIONAL_PROVIDER_IGNORE := $(addprefix --ignore=,$(PYTEST_PROVIDER_CONTEXTUALIZATION_PATHS) $(PYTEST_LEGACY_GRAPH_PATHS))



help: ## Show this help message
	@echo "$(BLUE)Contextual RAG v$(PROJECT_VERSION) - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@grep -E '^[a-zA-Z0-9_%-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

install: ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	uv sync --no-dev
	@echo "$(GREEN)✓ Production dependencies installed$(NC)"

install-dev: ## Install development dependencies (linters, formatters, etc.)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	uv sync
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

install-all: ## Install all dependencies (prod + dev + docs)
	@echo "$(BLUE)Installing all dependencies...$(NC)"
	uv sync --all-extras --all-groups
	@echo "$(GREEN)✓ All dependencies installed$(NC)"

# =============================================================================
# UV DEPENDENCY MANAGEMENT
# =============================================================================

lock: ## Generate/update uv.lock from pyproject.toml
	@echo "$(BLUE)Updating lock file...$(NC)"
	uv lock
	@echo "$(GREEN)✓ Lock file updated$(NC)"

update: ## Update all dependencies to latest versions
	@echo "$(BLUE)Upgrading all dependencies...$(NC)"
	uv lock --upgrade
	@echo "$(GREEN)✓ Dependencies upgraded$(NC)"

update-pkg: ## Update specific package (usage: make update-pkg PKG=requests)
ifndef PKG
	$(error PKG is required. Usage: make update-pkg PKG=requests)
endif
	@echo "$(BLUE)Upgrading $(PKG)...$(NC)"
	uv lock --upgrade-package $(PKG)
	@echo "$(GREEN)✓ $(PKG) upgraded$(NC)"

reinstall: ## Clean venv and reinstall all dependencies
	@echo "$(BLUE)Reinstalling dependencies...$(NC)"
	rm -rf .venv
	uv sync
	@echo "$(GREEN)✓ Dependencies reinstalled$(NC)"

setup-hooks: ## Install pre-commit hooks
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
	@echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

local-pr-ready: ## Full PR readiness gate (check + unit tests) - run manually
	@echo "$(BLUE)Running full PR readiness gate...$(NC)"
	make check
	@echo "$(BLUE)Running core unit tests...$(NC)"
	make test-unit
	@echo "$(GREEN)✓ Full PR readiness gate passed$(NC)"

# =============================================================================
# CODE QUALITY CHECKS
# =============================================================================

lint: ## Run Ruff linter (fast)
	@echo "$(BLUE)Running Ruff linter...$(NC)"
	uv run --frozen ruff check $(LINT_PATHS)
	@echo "$(GREEN)✓ Ruff check complete$(NC)"

lint-fix: ## Run Ruff linter with auto-fix
	@echo "$(BLUE)Running Ruff with auto-fix...$(NC)"
	uv run ruff check $(LINT_PATHS) --fix
	@echo "$(GREEN)✓ Ruff auto-fix complete$(NC)"

format: ## Format code with Ruff
	@echo "$(BLUE)Formatting code with Ruff...$(NC)"
	uv run ruff format $(LINT_PATHS)
	@echo "$(GREEN)✓ Code formatted$(NC)"

format-check: ## Check if code is formatted
	@echo "$(BLUE)Checking code format...$(NC)"
	uv run ruff format $(LINT_PATHS) --check
	@echo "$(GREEN)✓ Format check complete$(NC)"

type-check: ## Run MyPy type checking
	@echo "$(BLUE)Running MyPy type checking...$(NC)"
	uv run --frozen mypy $(LINT_PATHS) --ignore-missing-imports --no-error-summary
	@echo "$(GREEN)✓ Type check complete$(NC)"

pylint: ## Run Pylint (comprehensive linting)
	@echo "$(BLUE)Running Pylint...$(NC)"
	uv run pylint $(LINT_PATHS) --rcfile=pyproject.toml || true
	@echo "$(GREEN)✓ Pylint check complete$(NC)"

security: ## Run Bandit security scan + Vulture dead-code check
	@echo "$(BLUE)Running Bandit security checks...$(NC)"
	uv run bandit -r $(LINT_PATHS) -c pyproject.toml
	@echo "$(GREEN)✓ Bandit security check complete$(NC)"
	@echo "$(BLUE)Checking for dead code with Vulture...$(NC)"
	uv run vulture $(LINT_PATHS) --min-confidence 80 --exclude "*site-packages*,*dist-info*,__pycache__,.pytest_cache,.ruff_cache,.mypy_cache,*.egg-info,.venv*"
	@echo "$(GREEN)✓ Vulture dead-code check complete$(NC)"

dead-code: ## Find dead code with Vulture (alias for security)
	@echo "$(BLUE)Checking for dead code...$(NC)"
	uv run vulture $(LINT_PATHS) --min-confidence 80 --exclude "*site-packages*,*dist-info*,__pycache__,.pytest_cache,.ruff_cache,.mypy_cache,*.egg-info,.venv*"
	@echo "$(GREEN)✓ Dead code check complete$(NC)"

compile-python: ## Compile all repo-tracked Python files (#2320)
	@echo "$(BLUE)Checking repo-tracked Python syntax...$(NC)"
	@tmp_file="$$(mktemp)"; \
	trap 'rm -f "$$tmp_file"' EXIT; \
	git ls-files '*.py' > "$$tmp_file"; \
	uv run python -m compileall -q -i "$$tmp_file"
	@echo "$(GREEN)✓ Repo-tracked Python syntax OK$(NC)"

all-checks: lint type-check security ## Run all code quality checks
	@echo "$(GREEN)✓✓✓ All checks passed! ✓✓✓$(NC)"

# =============================================================================
# TESTING
# =============================================================================

test: ## Run deterministic core PR/local gate (core + graph paths + no-service lane)
	@echo "$(BLUE)Running deterministic core gate (test-core + graph_paths + no-service lane)...$(NC)"
	$(MAKE) test-core
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/integration/test_graph_paths.py -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	$(MAKE) test-no-service-lane
	@echo "$(GREEN)✓ Deterministic core gate complete$(NC)"

test-no-service-lane: ## Run no-service integration/smoke lane (#2324 Phase 1.2)
	@echo "$(BLUE)Running no-service integration/smoke lane (-m no_services)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/integration tests/smoke -q --timeout=30 -m "no_services and not requires_extras and not slow"
	@echo "$(GREEN)✓ No-service integration/smoke lane complete$(NC)"

test-core: ## Run monolith core-required tests only (local/manual)
	@echo "$(BLUE)Running monolith core test gate...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest \
	  tests/unit/core/ \
	  tests/unit/runtime/ \
	  tests/regression/ \
	  tests/contract/test_runtime_no_telegram_bot_coupling_contract.py \
	  tests/contract/test_layering_no_telegram_bot_imports_contract.py \
	  tests/contract/test_langfuse_optional_core_contract.py \
	  --ignore=tests/unit/core/test_pipeline.py \
	  -q --timeout=30 -m "not requires_extras and not slow"
	@echo "$(GREEN)✓ Monolith core test gate complete$(NC)"

test-telegram-adapter: ## Run Telegram adapter unit tests explicitly
	@echo "$(BLUE)Running Telegram adapter tests...$(NC)"
	uv sync --extra telegram --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_TELEGRAM_ADAPTER_PATHS) $(PYTEST_TELEGRAM_ADAPTER_ROOT_TESTS) -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Telegram adapter tests complete$(NC)"


test-providers-extra: ## Run optional provider/contextualization tests explicitly
	@echo "$(BLUE)Running providers-extra tests...$(NC)"
	uv sync --extra providers --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_PROVIDER_CONTEXTUALIZATION_PATHS) -q --timeout=30 -m "not legacy_api and not slow"
	@echo "$(GREEN)✓ Providers-extra tests complete$(NC)"


test-ingest-extra: ## Run optional ingestion-extra tests explicitly
	@echo "$(BLUE)Running ingestion-extra tests...$(NC)"
	uv sync --extra ingest --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ingestion/ -q --timeout=30
	@echo "$(GREEN)✓ Ingestion-extra tests complete$(NC)"





test-full: ## Run full test suite with hybrid parallelism (all tiers)
	@echo "$(BLUE)Running full test suite...$(NC)"
	uv sync --all-extras --all-groups
	@echo "$(BLUE)Phase 1/2: parallel-safe suites...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 RUN_BENCHMARK_TESTS=1 uv run pytest $(PYTEST_FULL_PARALLEL_DIRS) $(PYTEST_FULL_PARALLEL_ARGS) --timeout=30 $(PYTEST_ADDOPTS)
	@echo "$(BLUE)Phase 2/2: stateful/live suites sequentially...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_FULL_SEQUENTIAL_DIRS) --timeout=30 $(PYTEST_ADDOPTS)
	@echo "$(GREEN)✓ Full test suite complete$(NC)"

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest tests/ --cov=src --cov=telegram_bot --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ## Run broad unit test lane locally in parallel
	@echo "$(BLUE)Running broad unit tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB) $(PYTEST_OPTIONAL_PROVIDER_IGNORE) $(PYTEST_PARALLEL_ARGS) -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Broad unit tests complete$(NC)"

test-unit-loadscope: ## Run unit tests with loadscope (faster fixture reuse locally)
	@echo "$(BLUE)Running unit tests (loadscope)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB) $(PYTEST_OPTIONAL_PROVIDER_IGNORE) -n auto --dist=loadscope -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Unit tests (loadscope) complete$(NC)"

test-unit-full: ## Run all unit tests including optional-dep tests (nightly/main)
	@echo "$(BLUE)Running full unit tests (all extras)...$(NC)"
	uv sync --all-extras --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)✓ Full unit tests complete$(NC)"

test-unit-extras: ## Run optional-extra unit tests only
	@echo "$(BLUE)Running optional-extra unit tests...$(NC)"
	uv sync --all-extras --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "requires_extras"
	@echo "$(GREEN)✓ Optional-extra unit tests complete$(NC)"

test-contract: ## Run static contract tests (no Docker; optional SDK lanes excluded by markers)
	@echo "$(BLUE)Running static contract tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) pytest tests/contract/ -n auto --dist=worksteal -q --timeout=30
	@echo "$(GREEN)Static contract tests complete$(NC)"


test-fast: ## Run unit tests in parallel (honours $(PYTEST_PARALLEL_ARGS))
	@echo "$(BLUE)Running unit tests in parallel...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB) $(PYTEST_OPTIONAL_PROVIDER_IGNORE) $(PYTEST_PARALLEL_ARGS) -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Parallel tests complete$(NC)"

test-all-fast: ## Run unit tests + critical graph-path integration tests in parallel (no smoke; smoke needs live services via 'make test-smoke')
	@echo "$(BLUE)Running unit + critical graph-path integration tests in parallel...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ tests/integration/test_graph_paths.py $(PYTEST_REQUIRES_EXTRAS_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB) $(PYTEST_OPTIONAL_PROVIDER_IGNORE) $(PYTEST_PARALLEL_ARGS) -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ All fast tests complete$(NC)"

test-lf: ## Run only last failed tests (parallel)
	@echo "$(BLUE)Running last failed tests...$(NC)"
	uv run pytest tests/unit/ --lf -n auto -q
	@echo "$(GREEN)✓ Last failed tests complete$(NC)"

test-ff: ## Run failed first, then rest
	@echo "$(BLUE)Running failed first...$(NC)"
	uv run pytest tests/unit/ --ff -v
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-profile: ## Profile slowest tests (find bottlenecks) — measures the same lane as test-unit
	@echo "$(BLUE)Profiling slow tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE) $(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB) $(PYTEST_OPTIONAL_PROVIDER_IGNORE) $(PYTEST_PARALLEL_ARGS) --durations=20 --durations-min=0.5 -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Profile complete$(NC)"

test-integration: ## Run graph path integration tests (no Docker, ~5s)
	@echo "$(BLUE)Running integration tests...$(NC)"
	uv run pytest tests/integration/test_graph_paths.py -v --timeout=30
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

test-integration-full: ## Run ALL integration tests (requires Docker)
	@echo "$(BLUE)Running full integration tests...$(NC)"
	uv run pytest tests/integration/ -v --timeout=60
	@echo "$(GREEN)✓ Full integration tests complete$(NC)"

test-nightly: ## Run heavy test suites (chaos, smoke, slow unit) — schedule overnight
	@echo "$(BLUE)Running nightly test suite...$(NC)"
	uv run pytest tests/chaos/ -v --timeout=60 -n auto -m "not legacy_api"
	uv run pytest tests/smoke/ -v --timeout=60 -m "not legacy_api"
	@set +e; \
	uv run pytest tests/unit/ -n auto --timeout=30 -m "slow" -q; \
	rc=$$?; \
	if [ $$rc -eq 5 ]; then \
		echo "$(YELLOW)No slow-marked unit tests collected; treating as success.$(NC)"; \
	elif [ $$rc -ne 0 ]; then \
		exit $$rc; \
	fi
	@echo "$(GREEN)✓ Nightly tests complete$(NC)"

test-store-durations: ## Update .test_durations for pytest-split CI sharding
	@echo "$(BLUE)Generating test duration data...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 $(UV_RUN_NO_SYNC) --python $(PYTHON_VERSION) pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) --store-durations $(PYTEST_PARALLEL_ARGS) --timeout=30 -m "not legacy_api and not requires_extras and not slow" -q
	@echo "$(GREEN)✓ .test_durations updated — commit this file$(NC)"

test-all: ## Run all tests with coverage threshold (CI mode)
	@echo "$(BLUE)Running all tests with coverage...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/ -v -n auto --cov=src --cov=telegram_bot --cov-report=term-missing --cov-fail-under=80
	@echo "$(GREEN)✓ All tests passed with 80%+ coverage$(NC)"

.PHONY: test-all-local

test-all-local: ## Run all local test suites (pytest all tiers)
	@echo "$(BLUE)Running all local test suites...$(NC)"
	make test-full
	@echo "$(GREEN)✓ All local test suites complete$(NC)"

# =============================================================================
# SMOKE & LOAD TESTS
# =============================================================================

test-preflight: ## Run preflight checks (Qdrant/Redis config)
	@echo "$(BLUE)Running preflight checks...$(NC)"
	uv run pytest tests/smoke/test_preflight.py -v -s
	@echo "$(GREEN)✓ Preflight complete$(NC)"

test-smoke: ## Run smoke tests (requires live services)
	@echo "$(BLUE)Running smoke tests...$(NC)"
	uv run pytest tests/smoke/ -v --tb=short
	@echo "$(GREEN)✓ Smoke tests complete$(NC)"

test-load-eviction: ## Run Redis eviction tests
	@echo "$(BLUE)Running Redis eviction tests...$(NC)"
	REDIS_URL="$${REDIS_URL:-redis://localhost:6379}" \
	uv run pytest tests/load/test_load_redis_eviction.py -v -s
	@echo "$(GREEN)✓ Redis eviction tests complete$(NC)"

smoke-fast: ## Quick zoo smoke (~30 sec, bash only)
	@echo "$(BLUE)Running quick zoo smoke...$(NC)"
	./scripts/smoke-zoo.sh
	@echo "$(GREEN)✓ Zoo smoke complete$(NC)"

smoke-zoo: ## Run zoo smoke tests (pytest)
	@echo "$(BLUE)Running zoo smoke tests...$(NC)"
	uv run pytest tests/smoke/test_zoo_smoke.py -v
	@echo "$(GREEN)✓ Zoo smoke tests complete$(NC)"

# =============================================================================
# REDIS VERIFICATION
# =============================================================================

.PHONY: test-redis

test-redis: ## Verify Redis Query Engine is available
	@echo "$(BLUE)Testing Redis Query Engine...$(NC)"
	@redis_policy=$$(docker exec $(REDIS_CONTAINER) redis-cli CONFIG GET maxmemory-policy | tail -n 1); \
		if [ "$$redis_policy" != "volatile-lfu" ]; then \
			echo "$(RED)FAIL: maxmemory-policy is $$redis_policy (expected volatile-lfu)$(NC)"; \
			exit 1; \
		fi; \
		echo "  maxmemory-policy: $$redis_policy"
	@redis_samples=$$(docker exec $(REDIS_CONTAINER) redis-cli CONFIG GET maxmemory-samples | tail -n 1); \
		if [ "$$redis_samples" != "$(EXPECTED_MAXMEMORY_SAMPLES)" ]; then \
			echo "$(RED)FAIL: maxmemory-samples is $$redis_samples (expected $(EXPECTED_MAXMEMORY_SAMPLES))$(NC)"; \
			exit 1; \
		fi; \
		echo "  maxmemory-samples: $$redis_samples"
	@docker exec $(REDIS_CONTAINER) redis-cli FT._LIST > /dev/null 2>&1 || \
		(echo "$(RED)FAIL: FT._LIST not available - Query Engine missing$(NC)" && exit 1)
	@echo "  FT._LIST: OK"
	@docker exec $(REDIS_CONTAINER) redis-cli FT.CREATE __test_vec_idx ON HASH PREFIX 1 __test_vec: SCHEMA name TEXT vec VECTOR FLAT 6 TYPE FLOAT32 DIM 4 DISTANCE_METRIC COSINE > /dev/null 2>&1 || \
		(echo "$(RED)FAIL: Cannot create VECTOR index$(NC)" && exit 1)
	@echo "  FT.CREATE VECTOR: OK"
	@docker exec $(REDIS_CONTAINER) redis-cli FT.DROPINDEX __test_vec_idx > /dev/null 2>&1 || true
	@echo "$(GREEN)Query Engine + Vector Search: OK$(NC)"
	@if [ "$${REQUIRE_REDIS_JSON:-0}" = "1" ]; then \
		docker exec $(REDIS_CONTAINER) redis-cli JSON.SET __test_json '$$' '{"test":1}' > /dev/null 2>&1 || \
			(echo "$(RED)FAIL: JSON.SET not available$(NC)" && exit 1); \
		docker exec $(REDIS_CONTAINER) redis-cli JSON.GET __test_json > /dev/null 2>&1 || \
			(echo "$(RED)FAIL: JSON.GET not available$(NC)" && exit 1); \
		docker exec $(REDIS_CONTAINER) redis-cli DEL __test_json > /dev/null 2>&1 || true; \
		echo "  JSON: OK"; \
	fi
	@echo "$(GREEN)✓ Redis capabilities verified$(NC)"

.PHONY: test-bot-health test-bot-health-vps preflight-bot bot-response-smoke

PREFLIGHT_BOT_FLAGS ?=
BOT_RESPONSE_SMOKE_FLAGS ?=

preflight-qdrant: ## Fail fast when localhost:6333 is unreachable (run before preflight-bot and bot)
	@if ! timeout 1 bash -c 'echo >/dev/tcp/localhost/6333' 2>/dev/null; then \
		echo "$(RED)✗ Qdrant is not reachable on localhost:6333$(NC)" >&2; \
		echo "$(YELLOW)Run 'make local-up' to start required local services (redis, qdrant, bge-m3)$(NC)" >&2; \
		exit 1; \
	fi
	@echo "$(GREEN)✓ Qdrant reachable$(NC)"

preflight-bot: ## Check bot runtime env before starting (missing .env, invalid token, port issues)
	@$(UV_RUN_NO_SYNC) python -m scripts.probe.check_bot_runtime_env $(PREFLIGHT_BOT_FLAGS)

bot-response-smoke: ## End-to-end gate: prove `make bot` actually answers a Telegram message (#2192)
	@echo "$(BLUE)Running bot response smoke gate...$(NC)"
	@uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python -m scripts.probe.bot_response_smoke $(BOT_RESPONSE_SMOKE_FLAGS)
	@echo "$(GREEN)✓ Bot response smoke gate passed$(NC)"

test-bot-health: ## Preflight: verify local native-bot prerequisites (Redis/Qdrant/LiteLLM + optional Postgres note)
	@echo "$(BLUE)Running bot health preflight...$(NC)"
	@set -a; if [ -f .env ]; then . ./.env; else . tests/fixtures/compose.ci.env; fi; set +a; \
	./scripts/probe/bot_health.sh
	@echo "$(GREEN)✓ Bot health preflight passed$(NC)"

test-bot-health-vps: ## Preflight: verify Qdrant + LLM from inside Docker network (VPS)
	@echo "$(BLUE)Running VPS bot health preflight...$(NC)"
	@docker compose exec bot python -c "\
	import urllib.request, json, sys; \
	r = json.loads(urllib.request.urlopen('http://qdrant:6333/collections', timeout=10).read()); \
	names = [c['name'] for c in r['result']['collections']]; \
	print(f'  Qdrant collections: {names}'); \
	assert 'gdrive_documents_bge' in names, 'gdrive_documents_bge not found'; \
	print('  ✓ Qdrant OK'); \
	"
	@echo "$(GREEN)✓ VPS bot health preflight passed$(NC)"

# =============================================================================
# PROJECT MANAGEMENT
# =============================================================================

clean: ## Clean up cache files and build artifacts
	@echo "$(BLUE)Cleaning up...$(NC)"
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned up$(NC)"

docker-clean: ## Prune Docker build cache and stopped containers (safe)
	@echo "$(BLUE)Pruning Docker build cache...$(NC)"
	docker builder prune -f --filter "until=720h" 2>/dev/null || true
	@echo "$(BLUE)Removing stopped containers...$(NC)"
	docker container prune -f 2>/dev/null || true
	@echo "$(GREEN)✓ Docker cleaned$(NC)"

docker-clean-aggressive: ## Prune ALL unused Docker resources (images, volumes, networks)
	@echo "$(YELLOW)WARNING: Aggressive cleanup — removes unused images and volumes$(NC)"
	docker system prune -f --volumes 2>/dev/null || true
	@echo "$(GREEN)✓ Docker aggressively cleaned$(NC)"

docker-clean-orphan-worktree-volumes: ## Report Docker volumes from removed git worktrees (dry-run, see #1546)
	@bash scripts/cleanup_orphaned_worktree_volumes.sh

docker-clean-orphan-worktree-volumes-apply: ## Delete Docker volumes from removed git worktrees (destructive, see #1546)
	@bash scripts/cleanup_orphaned_worktree_volumes.sh --apply

# =============================================================================
# DOCKER PROFILES
# =============================================================================

# Common compose command with --compatibility to enforce deploy.resources.limits
COMPOSE_CMD := docker compose --compatibility
LOCAL_COMPOSE_FILE := compose.yml:compose.dev.yml
CORE_MIN_COMPOSE_FILE := compose.core.yml
# Local dev env fallback: use .env if present, otherwise safe CI fixture values
LOCAL_COMPOSE_CMD := COMPOSE_FILE=$(LOCAL_COMPOSE_FILE) $(COMPOSE_CMD) --env-file $$( [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env )
# Runtime env for E2E trace gates: allow worktrees to point at the main checkout .env
RAG_RUNTIME_ENV_FILE ?= $(shell [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env)
export RAG_RUNTIME_ENV_FILE

# =============================================================================
# REMOTE MACBOOK DOCKER HOST
# =============================================================================

# Set these three vars in your shell/.env before using remote-* targets:
#   REMOTE_DOCKER_HOST  – SSH hostname for the remote Docker host
#   REMOTE_DOCKER_IP    – LAN IP of the remote Docker host
#   REMOTE_DOCKER_REPO  – absolute path to rag-fresh checkout on remote
REMOTE_DOCKER_HOST ?=
REMOTE_DOCKER_IP ?=
REMOTE_DOCKER_REPO ?=
REMOTE_DOCKER_PATH ?= /opt/homebrew/bin:/usr/local/bin
REMOTE_COMPOSE_FILE ?= compose.yml:compose.dev.yml
REMOTE_BGE_M3_MEMORY_LIMIT ?= 6G
REMOTE_SSH := ssh $(REMOTE_DOCKER_HOST)

REMOTE_CORE_SERVICES := postgres redis qdrant bge-m3 user-base bot

remote-docker-status: ## Remote Docker diagnostics: hostname, git, Colima, Docker/buildx versions
	@echo "$(BLUE)Remote Docker status ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) " \
		echo \"Hostname: \`hostname\`\"; \
		echo \"Repo: $(REMOTE_DOCKER_REPO)\"; \
		cd $(REMOTE_DOCKER_REPO) && echo \"Git branch: \`git branch --show-current 2>/dev/null || echo N/A\`\" && echo \"Last commit: \`git log -1 --format=%h 2>/dev/null || echo N/A\`\"; \
		export PATH=$(REMOTE_DOCKER_PATH):\$$PATH; \
		echo \"Colima status:\"; \
		colima status 2>/dev/null || echo \"  Colima not running or not found\"; \
		echo \"Docker client: \`docker version --format '{{.Client.Version}}' 2>/dev/null || echo N/A\`\"; \
		echo \"Docker server: \`docker version --format '{{.Server.Version}}' 2>/dev/null || echo N/A\`\"; \
		echo \"Buildx version: \`docker buildx version 2>/dev/null || echo 'buildx not available'\`\"; \
	"

remote-compose-config: ## Render remote Compose config (service names only, no secrets)
	@echo "$(BLUE)Remote Compose config ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` config --services"

remote-docker-ps: ## Show remote Compose container names, status, and ports
	@echo "$(BLUE)Remote Docker containers ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'"

remote-env-sync: ## Sync local .env to remote MacBook repo (fails if local .env missing)
	@echo "$(BLUE)Syncing .env to remote $(REMOTE_DOCKER_HOST)...$(NC)"
	@test -f .env || { echo "$(RED)Error: local .env not found$(NC)"; exit 1; }
	@scp -q .env $(REMOTE_DOCKER_HOST):$(REMOTE_DOCKER_REPO)/.env
	@echo "$(GREEN)✓ .env synced to remote$(NC)"

remote-env-check: ## Verify remote .env exists and report missing required variable names
	@echo "$(BLUE)Checking remote .env on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && \
		if [ ! -f .env ]; then echo 'Error: remote .env not found'; exit 1; fi; \
		missing=''; \
		if ! grep -qE '^TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN] .env; then missing=\"$$missing TELEGRAM_BOT_TOKEN\"; fi; \
		if ! grep -qE '^(CEREBRAS_API_KEY|GROQ_API_KEY|OPENAI_API_KEY)=' .env; then missing=\"$$missing (CEREBRAS_API_KEY|GROQ_API_KEY|OPENAI_API_KEY)\"; fi; \
		if ! grep -qE '^NEXTAUTH_SECRET=' .env; then missing=\"$$missing NEXTAUTH_SECRET\"; fi; \
		if ! grep -qE '^SALT=' .env; then missing=\"$$missing SALT\"; fi; \
		if ! grep -qE '^ENCRYPTION_KEY=' .env; then missing=\"$$missing ENCRYPTION_KEY\"; fi; \
		if [ -n \"$$missing\" ]; then \
			echo \"Missing variables:$$missing\"; \
			exit 1; \
		else \
			echo 'Required variables present'; \
		fi"


remote-core-up: ## Start minimal RAG bot core on remote MacBook Docker
	@echo "$(BLUE)Starting minimal RAG bot core on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile bot up -d $(REMOTE_CORE_SERVICES)"
	@echo "$(GREEN)Remote core stack started$(NC)"

remote-core-ps: ## Show remote core container status
	@echo "$(BLUE)Remote core containers ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' $(REMOTE_CORE_SERVICES)"

remote-core-logs: ## Show recent remote core logs
	@echo "$(BLUE)Remote core logs ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` logs --tail 100 $(REMOTE_CORE_SERVICES)"


remote-bot-up: ## Start remote bot container
	@echo "$(BLUE)Starting remote bot on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile bot up -d bot"
	@echo "$(GREEN)✓ Remote bot started$(NC)"

remote-bot-restart: ## Recreate remote bot container
	@echo "$(BLUE)Restarting remote bot on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile bot up -d --force-recreate bot"
	@echo "$(GREEN)✓ Remote bot restarted$(NC)"

remote-bot-logs: ## Show recent remote bot logs
	@echo "$(BLUE)Remote bot logs ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` logs --tail 100 bot"

remote-local-up: ## Start the local-service subset on remote MacBook Docker
	@echo "$(BLUE)Starting local service subset on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` up -d $(LOCAL_SERVICES)"
	@echo "$(GREEN)✓ Local service subset started on remote$(NC)"

remote-local-down: ## Stop remote MacBook compose stack
	@echo "$(BLUE)Stopping remote stack on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile full down"
	@echo "$(GREEN)✓ Remote stack stopped$(NC)"

remote-local-logs: ## Show recent remote MacBook compose logs
	@echo "$(BLUE)Remote compose logs ($(REMOTE_DOCKER_HOST))...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile full logs --tail 120"
	@echo "$(GREEN)✓ Remote compose logs shown$(NC)"

remote-core-health: ## Check minimal RAG bot core health on remote MacBook Docker
	@echo "$(BLUE)Remote core health ($(REMOTE_DOCKER_HOST))...$(NC)"
	@fail=0; \
	if ! $(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` exec -T bot python - <<'PY'\nimport socket, sys\nfailed=[]\nfor host, port in [('qdrant',6333),('bge-m3',8000),('postgres',5432),('redis',6379)]:\n    s=socket.socket(); s.settimeout(5)\n    try:\n        s.connect((host, port)); print(f'  ok: {host}:{port}')\n    except Exception as exc:\n        failed.append(f'{host}:{port} -> {exc}')\n    finally:\n        s.close()\nif failed:\n    print('\n'.join(failed), file=sys.stderr); sys.exit(1)\nPY"; then fail=1; fi; \
	bot_restarts=$$($(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && cid=\$$(COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` ps -q bot 2>/dev/null); if [ -n \"\$$cid\" ]; then docker inspect --format='{{.RestartCount}}' \$$cid 2>/dev/null; else echo N/A; fi"); \
	if [ "$$bot_restarts" != "N/A" ]; then echo "  Bot: running (restarts: $$bot_restarts)"; else echo "  Bot: $(RED)container not found$(NC)"; fail=1; fi; \
	exit $$fail

remote-core-env-check: ## Verify core-only required variables in remote .env
	@echo "$(BLUE)Checking core env on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && \
		if [ ! -f .env ]; then echo 'Error: remote .env not found'; exit 1; fi; \
		missing=''; \
		if ! grep -qE '^TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN] .env; then missing=\"$$missing TELEGRAM_BOT_TOKEN\"; fi; \
		if ! grep -qE '^(CEREBRAS_API_KEY|GROQ_API_KEY|OPENAI_API_KEY)=' .env; then missing=\"$$missing (CEREBRAS_API_KEY|GROQ_API_KEY|OPENAI_API_KEY)\"; fi; \
		if [ -n \"$$missing\" ]; then \
			echo \"Missing variables:$$missing\"; \
			exit 1; \
		else \
			echo 'Core required variables present'; \
		fi"

remote-service-health: ## Check remote service health over SSH on 127.0.0.1
	@echo "$(BLUE)Remote service health ($(REMOTE_DOCKER_HOST))...$(NC)"
	@fail=0; \
	if ! $(REMOTE_SSH) "curl -fsS http://127.0.0.1:6333/readyz >/dev/null 2>&1"; then echo "  Qdrant: $(RED)FAIL$(NC)"; fail=1; else echo "  Qdrant: $(GREEN)OK$(NC)"; fi; \
	if ! $(REMOTE_SSH) "curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1"; then echo "  BGE-M3: $(RED)FAIL$(NC)"; fail=1; else echo "  BGE-M3: $(GREEN)OK$(NC)"; fi; \
	if $(REMOTE_SSH) "curl -fsS http://127.0.0.1:3001/api/public/health >/dev/null 2>&1"; then echo "  Langfuse: $(GREEN)OK$(NC)"; else echo "  Langfuse: $(YELLOW)NOT READY$(NC)"; fi; \
	if $(REMOTE_SSH) "curl -fsS http://127.0.0.1:5001/health >/dev/null 2>&1"; then echo "  Docling: $(GREEN)OK$(NC)"; else echo "  Docling: $(YELLOW)NOT READY$(NC)"; fi; \
	bot_restarts=$$($(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && cid=\$$(COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` ps -q bot 2>/dev/null); if [ -n \"\$$cid\" ]; then docker inspect --format='{{.RestartCount}}' \$$cid 2>/dev/null; else echo N/A; fi"); \
	if [ "$$bot_restarts" != "N/A" ]; then echo "  Bot: running (restarts: $$bot_restarts)"; else echo "  Bot: $(YELLOW)container not found$(NC)"; fi; \
	exit $$fail

.PHONY: core-min-up core-up docker-core-up docker-bot-up docker-ai-up docker-ingest-up docker-full-up docker-down docker-ps

core-min-up: ## Start minimal core services only (qdrant + redis)
	@echo "$(BLUE)Starting minimal core services (qdrant + redis)...$(NC)"
	COMPOSE_FILE=$(CORE_MIN_COMPOSE_FILE) $(COMPOSE_CMD) up -d
	@echo "$(GREEN)✓ Minimal core services started$(NC)"

core-up: docker-core-up ## Start the full default local compose core

docker-core-up: ## Start default local compose stack (unprofiled services)
	@echo "$(BLUE)Starting core services...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d
	@echo "$(GREEN)✓ Core services started$(NC)"

docker-bot-up: preflight-bot ## Start core + bot services (bot)
	@echo "$(BLUE)Starting bot services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile bot up -d
	@echo "$(GREEN)✓ Bot services started$(NC)"

docker-ai-up: ## Start core + heavy AI services (bge-m3, user-base)
	@echo "$(BLUE)Starting AI services...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d bge-m3
	@echo "$(GREEN)✓ AI services started$(NC)"

docker-ingest-up: ## Start core + ingestion service
	@echo "$(BLUE)Starting ingestion service...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile ingest up -d
	@echo "$(GREEN)✓ Ingestion service started$(NC)"

docker-full-up: ## Start all services (full stack)
	@echo "$(BLUE)Starting full stack...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile full up -d
	@echo "$(GREEN)✓ Full stack started$(NC)"

docker-up: docker-core-up ## Alias for docker-core-up (backward compat)

docker-down: ## Stop all Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile full down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docker-ps: ## Show Docker service status
	@echo "$(BLUE)Docker service status:$(NC)"
	@$(LOCAL_COMPOSE_CMD) --profile full ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# =============================================================================
# DEVELOPMENT WORKFLOW
# =============================================================================

dev-setup: install-dev docker-up ## Complete development setup
	@echo "$(GREEN)✓✓✓ Development environment ready! ✓✓✓$(NC)"
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Copy .env.example to .env"
	@echo "  2. Fill in your API keys"
	@echo "  3. Run 'make test' to verify setup"

pre-commit: lint-fix format type-check test ## Run all checks before commit
	@echo "$(GREEN)✓✓✓ Ready to commit! ✓✓✓$(NC)"

ci: format-check lint type-check security test ## CI/CD pipeline checks
	@echo "$(GREEN)✓✓✓ CI checks passed! ✓✓✓$(NC)"

# =============================================================================
# DOCUMENTATION
# =============================================================================

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)Starting documentation server...$(NC)"
	uv run mkdocs serve
	@echo "$(GREEN)✓ Documentation server running at http://localhost:8000$(NC)"

docs-build: ## Build documentation
	@echo "$(BLUE)Building documentation...$(NC)"
	uv run mkdocs build
	@echo "$(GREEN)✓ Documentation built in site/$(NC)"

docs-check: ## Check Markdown relative links for broken targets
	@echo "$(BLUE)Checking documentation links...$(NC)"
	python3 scripts/check_markdown_links.py
	@echo "$(GREEN)✓ Documentation links OK$(NC)"

# =============================================================================
# QUICK COMMANDS
# =============================================================================

.PHONY: check-frozen candidate-check

check: lint type-check ## Quick check (lint + types)
	@echo "$(GREEN)✓ Quick check complete$(NC)"

check-frozen: ## Read-only check: fail if .venv is stale, then lint + type-check without uv sync
	@echo "$(BLUE)Checking frozen uv environment...$(NC)"
	@uv sync --frozen --check || { \
		echo "$(RED)Environment is stale. Run 'uv sync --frozen' in an isolated worktree .venv, then retry.$(NC)"; \
		exit 1; \
	}
	@echo "$(BLUE)Running Ruff lint without uv auto-sync...$(NC)"
	@$(UV_RUN_NO_SYNC) ruff check $(LINT_PATHS)
	@echo "$(GREEN)✓ Ruff check complete$(NC)"
	@echo "$(BLUE)Running MyPy type-check without uv auto-sync...$(NC)"
	@$(UV_RUN_NO_SYNC) mypy $(LINT_PATHS) --ignore-missing-imports --no-error-summary
	@echo "$(GREEN)✓ Frozen check complete$(NC)"

candidate-check: check-frozen ## Candidate/review check alias (read-only after env preflight)

pre-push: lint format-check ## Pre-push gate (lint + format-check)
	@echo "$(GREEN)✓ Pre-push gate passed$(NC)"

fix: lint-fix format ## Fix all auto-fixable issues
	@echo "$(GREEN)✓ Auto-fixes applied$(NC)"

qa: all-checks test ## Full quality assurance
	@echo "$(GREEN)✓✓✓ Full QA complete! ✓✓✓$(NC)"

# =============================================================================
# Local Development (compose.yml + compose.dev.yml via COMPOSE_FILE env)
# =============================================================================


.PHONY: local-up local-up-ingest local-down local-logs local-ps local-build local-redis-recreate release-polling-lock run-bot bot
LOCAL_SERVICES := postgres redis qdrant bge-m3

LOCAL_INGEST_SERVICES := docling
LOCAL_ALL_SERVICES := $(LOCAL_SERVICES) $(LOCAL_INGEST_SERVICES)

local-up:  ## Start local Docker services (bot runs via make run-bot)
	$(LOCAL_COMPOSE_CMD) up -d $(LOCAL_SERVICES)
	@echo "$(GREEN)✓ Local services started. Run bot: make run-bot$(NC)"

local-up-ingest:  ## Start local services + docling for ingestion workflows
	$(LOCAL_COMPOSE_CMD) up -d $(LOCAL_ALL_SERVICES)
	@echo "$(GREEN)✓ Local services + docling started$(NC)"

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
	echo "$(GREEN)✓ Polling lock released. Run 'make run-bot' again.$(NC)"

run-bot:  ## Run bot locally (requires: make local-up)
	$(UV_RUN_NO_SYNC) --env-file "$$RAG_RUNTIME_ENV_FILE" python -m telegram_bot.main

bot: preflight-qdrant preflight-bot test-bot-health ## Alias: run bot (fail-fast when Qdrant is down; tee output to logs/bot-run.log)
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
		echo "$(YELLOW)logs/bot-run.log not found — run \`make bot\` first$(NC)"; \
		exit 1; \
	fi
	@tail -F logs/bot-run.log

bot-logs-errors:  ## Show recent ERROR/CRITICAL lines and Tracebacks from logs/bot-run.log
	@if [ ! -f logs/bot-run.log ]; then \
		echo "$(YELLOW)logs/bot-run.log not found — run \`make bot\` first$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Recent errors in logs/bot-run.log:$(NC)"
	@grep -nE 'ERROR|CRITICAL|Traceback|exception' logs/bot-run.log | tail -n $${BOT_LOG_LINES:-200} || \
		echo "$(GREEN)No error/critical lines found$(NC)"

bot-logs-startup:  ## Show recent startup/preflight events from logs/bot-run.log
	@if [ ! -f logs/bot-run.log ]; then \
		echo "$(YELLOW)logs/bot-run.log not found — run \`make bot\` first$(NC)"; \
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

local-build:  ## Rebuild local Docker services
	$(LOCAL_COMPOSE_CMD) build bge-m3 docling

local-redis-recreate:  ## Recreate local Redis container after REDIS_PASSWORD/.env changes
	@echo "$(BLUE)Recreating local Redis container with current .env values...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d --no-deps --force-recreate redis
	@echo "$(GREEN)✓ Local Redis recreated. Next: make test-bot-health$(NC)"

# =============================================================================
# Deployment
# =============================================================================

.PHONY: deploy-code deploy-release deploy-bot deploy-vps-local

deploy-code:  ## Quick deploy (git pull only)
	git tag -d deploy-code 2>/dev/null || true
	git tag deploy-code
	git push origin deploy-code --force

deploy-release:  ## Release deploy (requires VERSION, e.g., make deploy-release VERSION=2.6.0)
ifndef VERSION
	$(error VERSION is required. Usage: make deploy-release VERSION=2.6.0)
endif
	git tag v$(VERSION)
	git push origin v$(VERSION)

deploy-bot:  ## Show official deploy flow: PR to dev, then merge dev to main snapshot
	@echo "$(CYAN)Official deploy flow:$(NC)"
	@echo "  1. Commit locally"
	@echo "  2. Push your work branch"
	@echo "  3. Open PR to dev"
	@echo "  4. Stage runtime-sensitive changes with make remote-core-up"
	@echo "  5. Merge dev to main for deployment snapshots"
	@echo "$(GREEN)No direct push to main is performed by this target.$(NC)"

deploy-vps-local:  ## Fallback/manual deploy: manual instructions only (VPS scripts removed from public repo)
	@echo "$(CYAN)Manual deploy: use private operator runbooks or Docker Compose on VPS$(NC)"

# =============================================================================
# E2E TESTING
# =============================================================================

.PHONY: e2e-install e2e-generate-data e2e-index-data e2e-test e2e-core-live e2e-core-live-real-llm e2e-test-group e2e-telegram-test e2e-setup

e2e-install: ## Install E2E testing dependencies
	@echo "$(BLUE)Installing E2E dependencies...$(NC)"
	uv sync --group e2e
	@echo "$(GREEN)✓ E2E dependencies installed$(NC)"

e2e-generate-data: ## Generate test property data
	@echo "$(BLUE)Generating test properties...$(NC)"
	uv run python scripts/generate_test_properties.py
	@echo "$(GREEN)✓ Test data generated$(NC)"

e2e-index-data: ## Index test data into Qdrant
	@echo "$(BLUE)Indexing test properties...$(NC)"
	uv run python scripts/index_test_properties.py
	@echo "$(GREEN)✓ Test data indexed$(NC)"

e2e-test: ## Run pytest E2E suite (Docker/live services)
	@echo "$(BLUE)Running pytest E2E suite...$(NC)"
	uv run pytest tests/e2e/test_core_flows_live.py -v --tb=short -m "e2e and not legacy_api"
	@echo "$(GREEN)✓ Pytest E2E suite complete$(NC)"

e2e-core-live: ## Run simplification core live golden path (Qdrant + BGE-M3)
	@echo "$(BLUE)Running simplification core live E2E golden path...$(NC)"
	E2E_CORE_STRICT=1 $(CORE_LIVE_PYTEST)
	@echo "$(GREEN)✓ Simplification core live E2E complete$(NC)"

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
	@echo "$(GREEN)✓ Simplification core live real LLM E2E complete$(NC)"

e2e-telegram-test: ## Run Telegram userbot E2E runner (Telethon + judge)
	@echo "$(BLUE)Running Telegram E2E runner...$(NC)"
	uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py
	@echo "$(GREEN)✓ Telegram E2E runner complete$(NC)"

e2e-test-group: ## Run specific test group (usage: make e2e-test-group GROUP=filters)
	uv run python scripts/e2e/runner.py --group $(GROUP)

e2e-setup: e2e-install ## Full E2E setup on canonical collection
	@echo "$(YELLOW)Using canonical collection via E2E_COLLECTION_NAME (default: gdrive_documents_bge)$(NC)"
	@echo "$(GREEN)✓ E2E setup complete$(NC)"

# =============================================================================
# BASELINE & OBSERVABILITY
# =============================================================================

.PHONY: baseline-smoke baseline-load baseline-compile baseline-compare baseline-set baseline-report baseline-check

# Generate unique session ID from git commit
BASELINE_SESSION := smoke-$(shell git rev-parse --short HEAD)-$(shell date +%Y%m%d%H%M%S)
LOAD_SESSION := load-$(shell git rev-parse --short HEAD)-$(shell date +%Y%m%d%H%M%S)

baseline-smoke: ## Run smoke tests with Langfuse tracing
	@echo "$(BLUE)Running smoke tests with Langfuse tracing...$(NC)"
	@echo "$(YELLOW)Session: $(BASELINE_SESSION)$(NC)"
	LANGFUSE_SESSION_ID="$(BASELINE_SESSION)" \
	LANGFUSE_RELEASE="$(shell git rev-parse --short HEAD)" \
	LANGFUSE_TRACING_ENABLED=true \
	uv run pytest tests/smoke/ -v --tb=short -x
	@echo ""
	@echo "$(GREEN)Results tagged as: $(BASELINE_SESSION)$(NC)"
	@echo "$(YELLOW)View in Langfuse: http://localhost:3001$(NC)"

baseline-load: ## Run load tests with Langfuse tracing
	@echo "$(BLUE)Running load tests with Langfuse tracing...$(NC)"
	@echo "$(YELLOW)Session: $(LOAD_SESSION)$(NC)"
	LANGFUSE_SESSION_ID="$(LOAD_SESSION)" \
	LANGFUSE_RELEASE="$(shell git rev-parse --short HEAD)" \
	LANGFUSE_TRACING_ENABLED=true \
	uv run pytest tests/load/ -v --tb=short
	@echo ""
	@echo "$(GREEN)Results tagged as: $(LOAD_SESSION)$(NC)"

baseline-compile: compile-python ## Backward-compatible baseline syntax gate (#2320)

baseline-compare: ## Compare current run against baseline (usage: make baseline-compare BASELINE_TAG=... CURRENT_SESSION=...)
ifndef BASELINE_TAG
	$(error BASELINE_TAG is required. Usage: make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=ci-abc-job-1)
endif
ifndef CURRENT_SESSION
	$(error CURRENT_SESSION is required.)
endif
	@echo "$(BLUE)Comparing baseline...$(NC)"
	uv run python -m tests.baseline.cli compare \
		--baseline-tag="$(BASELINE_TAG)" \
		--current-session="$(CURRENT_SESSION)" \
		--thresholds=tests/baseline/thresholds.yaml \
		--output="reports/baseline-$(CURRENT_SESSION).json"

baseline-set: ## Tag traces as baseline (usage: make baseline-set TAG=... SESSION_ID=...)
ifndef TAG
	$(error TAG is required. Usage: make baseline-set TAG=main-latest SESSION_ID=smoke-abc-20260128)
endif
ifndef SESSION_ID
	$(error SESSION_ID is required.)
endif
	@echo "$(BLUE)Setting $(TAG) as baseline...$(NC)"
	uv run python -m tests.baseline.cli set-baseline --tag="$(TAG)" --session-id="$(SESSION_ID)"

baseline-report: ## Generate HTML baseline report
ifndef BASELINE_TAG
	$(error BASELINE_TAG is required. Usage: make baseline-report BASELINE_TAG=... CURRENT_TAG=...)
endif
ifndef CURRENT_TAG
	$(error CURRENT_TAG is required. Usage: make baseline-report BASELINE_TAG=... CURRENT_TAG=...)
endif
	@echo "$(BLUE)Generating baseline report...$(NC)"
	uv run python -m tests.baseline.cli report \
		--baseline="$(BASELINE_TAG)" \
		--current="$(CURRENT_TAG)" \
		--thresholds=tests/baseline/thresholds.yaml \
		--output=reports/baseline-$(shell date +%Y%m%d-%H%M%S).html
	@echo "$(GREEN)Report saved to reports/$(NC)"

baseline-check: baseline-compile baseline-smoke ## Optional Langfuse baseline check (smoke + compare with main)
	@echo "$(BLUE)Comparing with main baseline...$(NC)"
	make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=$(BASELINE_SESSION)

# =============================================================================
# RAG EVALUATION (RAGAS + DeepEval)
# =============================================================================

.PHONY: eval-rag eval-rag-quick eval-rag-full

eval-rag: ## Run RAG evaluation with RAGAS metrics (faithfulness >= 0.8)
	@echo "$(BLUE)Running RAG evaluation with RAGAS...$(NC)"
	@echo "$(YELLOW)Dataset: tests/eval/ground_truth.json (55 samples)$(NC)"
	@echo "$(YELLOW)LLM: $(EVAL_MODEL) via LiteLLM SDK router$(NC)"
	LANGFUSE_TRACING_ENABLED=true \
	uv run python -m src.evaluation.ragas_evaluation
	@echo "$(GREEN)✓ RAG evaluation complete$(NC)"

eval-rag-quick: ## Quick RAG evaluation (10 samples)
	@echo "$(BLUE)Running quick RAG evaluation...$(NC)"
	EVAL_SAMPLE_SIZE=10 \
	uv run python -m src.evaluation.ragas_evaluation
	@echo "$(GREEN)✓ Quick evaluation complete$(NC)"

eval-rag-full: ## Full RAG evaluation with all metrics
	@echo "$(BLUE)Running full RAG evaluation...$(NC)"
	LANGFUSE_TRACING_ENABLED=true \
	EVAL_INCLUDE_DEEPEVAL=true \
	uv run python -m src.evaluation.ragas_evaluation
	@echo "$(GREEN)✓ Full evaluation complete$(NC)"

.PHONY: eval-goldset-sync eval-experiment

eval-goldset-sync: ## Sync gold set to Langfuse dataset
	@echo "$(BLUE)Syncing gold set to Langfuse...$(NC)"
	uv run python scripts/eval/goldset_sync.py
	@echo "$(GREEN)✓ Gold set synced$(NC)"

eval-experiment: ## Run RAG experiment on gold set
	@echo "$(BLUE)Running RAG experiment...$(NC)"
	uv run python scripts/eval/run_experiment.py
	@echo "$(GREEN)✓ Experiment complete$(NC)"

.PHONY: eval-gold-gen eval-gold-gen-dry eval-sdk-experiment eval-sdk-experiment-named

eval-gold-gen: ## Generate gold set from Qdrant → Langfuse Dataset + JSONL
	@echo "$(BLUE)Generating gold set from Qdrant...$(NC)"
	uv run python scripts/generate_gold_set.py --collection gdrive_documents_bge

eval-gold-gen-dry: ## Dry-run gold set generation (JSONL only, no Langfuse)
	@echo "$(BLUE)Generating gold set (dry-run)...$(NC)"
	uv run python scripts/generate_gold_set.py --dry-run --output data/gold_set.jsonl

eval-sdk-experiment: ## Run SDK experiment on gold set (DATASET=name required)
	@echo "$(BLUE)Running SDK experiment on gold set...$(NC)"
	uv run python scripts/run_experiment.py --dataset $(DATASET)

eval-sdk-experiment-named: ## Run named SDK experiment (DATASET=name NAME=label required)
	@echo "$(BLUE)Running SDK experiment '$(NAME)'...$(NC)"
	uv run python scripts/run_experiment.py --dataset $(DATASET) --name $(NAME)

# =============================================================================
# GOOGLE DRIVE SYNC (rclone)
# =============================================================================
# rclone sync scripts were removed from public repo.
# See docs/GDRIVE_INGESTION.md for ingestion setup.
	@tail -10 /var/log/rclone-sync.log 2>/dev/null || echo "No logs yet"

# =============================================================================
# DOCUMENT INGESTION (CocoIndex Pipeline)
# =============================================================================

.PHONY: ingest-setup ingest-dir ingest-status ingest-services ingest-test

ingest-setup: ## Setup ingestion (DB + Qdrant indexes)
	@echo "$(BLUE)Setting up ingestion infrastructure...$(NC)"
	uv run python scripts/setup_ingestion_collection.py
	@echo "$(GREEN)✓ Ingestion setup complete$(NC)"

ingest-test: ## Run ingestion unit tests
	@echo "$(BLUE)Running ingestion tests...$(NC)"
	uv run pytest tests/unit/test_ingestion*.py tests/unit/test_docling*.py tests/unit/test_chunker.py tests/unit/test_cocoindex*.py -v
	@echo "$(GREEN)✓ Ingestion tests complete$(NC)"

ingest-dir: ## Ingest documents from directory (usage: make ingest-dir DIR=path/to/docs)
ifndef DIR
	$(error DIR is required. Usage: make ingest-dir DIR=path/to/docs)
endif
	@echo "$(BLUE)Ingesting documents from $(DIR)...$(NC)"
	uv run python -m telegram_bot.services.ingestion_cocoindex ingest-dir "$(DIR)"
	@echo "$(GREEN)✓ Directory ingestion complete$(NC)"

ingest-status: ## Show collection statistics
	@echo "$(BLUE)Collection status:$(NC)"
	uv run python -m telegram_bot.services.ingestion_cocoindex status

ingest-services: ## Index curated services.yaml content into Qdrant
	@echo "$(BLUE)Indexing services.yaml content...$(NC)"
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; uv run python -m scripts.index_services
	@echo "$(GREEN)✓ services.yaml indexing complete$(NC)"

# =============================================================================
# UNIFIED INGESTION PIPELINE (v3.2.1)
# =============================================================================

.PHONY: ingest-unified-preflight ingest-unified-bootstrap ingest-unified ingest-unified-watch ingest-unified-status ingest-unified-reprocess ingest-unified-logs

ingest-unified-preflight: ## Check unified ingestion dependencies and source path
	@echo "$(BLUE)Running unified ingestion preflight...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli preflight

ingest-unified-bootstrap: ## Create/validate unified ingestion collection schema
	@echo "$(BLUE)Bootstrapping unified ingestion collection...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli bootstrap --require-colbert

ingest-unified: ## Run unified ingestion once
	@echo "$(BLUE)Running unified ingestion (CocoIndex)...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli run
	@echo "$(GREEN)✓ Ingestion complete$(NC)"

ingest-unified-watch: ## Run unified ingestion continuously (watch mode)
	@echo "$(BLUE)Starting unified ingestion watch mode...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli run --watch

ingest-unified-status: ## Show unified ingestion status
	@echo "$(BLUE)Unified ingestion status:$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli status

ingest-unified-reprocess: ## Reprocess all error files
	@echo "$(BLUE)Reprocessing error files...$(NC)"
	@$(ENV_LOAD) uv run python -m src.ingestion.unified.cli reprocess --errors
	@echo "$(GREEN)✓ Reprocess queued$(NC)"

ingest-unified-logs: ## Show ingestion service logs
	docker compose logs ingestion -f --tail 100

# =============================================================================
# QDRANT BACKUP
# =============================================================================

.PHONY: qdrant-backup qdrant-cleanup

qdrant-backup: ## Create Qdrant collection snapshots (all collections)
	@echo "$(BLUE)Creating Qdrant snapshots...$(NC)"
	uv run python scripts/qdrant_snapshot.py
	@echo "$(GREEN)✓ Qdrant backup complete$(NC)"

qdrant-cleanup: ## Prune Qdrant storage: snapshot then trigger optimiser (#1545)
	@echo "$(YELLOW)Qdrant storage cleanup — issue #1545$(NC)"
	@echo "$(BLUE)Step 1/3: taking collection snapshot before cleanup...$(NC)"
	@QDRANT_URL=$${QDRANT_URL:-http://localhost:6333}; \
	COLLECTION=$${QDRANT_COLLECTION:-gdrive_documents_bge}; \
	result=$$(curl -sf -X POST "$$QDRANT_URL/collections/$$COLLECTION/snapshots" 2>&1); \
	if [ $$? -eq 0 ]; then \
		echo "$(GREEN)  ✓ Snapshot created for $$COLLECTION$(NC)"; \
	else \
		echo "$(YELLOW)  ⚠ Snapshot skipped (Qdrant may not be running): $$result$(NC)"; \
	fi
	@echo "$(BLUE)Step 2/3: requesting optimiser run on all segments...$(NC)"
	@QDRANT_URL=$${QDRANT_URL:-http://localhost:6333}; \
	COLLECTION=$${QDRANT_COLLECTION:-gdrive_documents_bge}; \
	result=$$(curl -sf -X PATCH "$$QDRANT_URL/collections/$$COLLECTION" \
		-H 'Content-Type: application/json' \
		-d '{"optimizers_config": {"indexing_threshold": 0}}' 2>&1); \
	if [ $$? -eq 0 ]; then \
		echo "$(GREEN)  ✓ Indexing threshold set to 0 — segments will be merged$(NC)"; \
		echo "$(BLUE)  Restoring indexing_threshold to 20000 kB...$(NC)"; \
		curl -sf -X PATCH "$$QDRANT_URL/collections/$$COLLECTION" \
			-H 'Content-Type: application/json' \
			-d '{"optimizers_config": {"indexing_threshold": 20000}}' > /dev/null && \
		echo "$(GREEN)  ✓ Indexing threshold restored to 20000 kB$(NC)"; \
	else \
		echo "$(YELLOW)  ⚠ Optimiser trigger skipped (Qdrant may not be running): $$result$(NC)"; \
	fi
	@echo "$(BLUE)Step 3/3: operator checklist$(NC)"
	@echo "  • Restart Qdrant to apply docker/qdrant/config.yaml changes:"
	@echo "      docker compose restart qdrant"
	@echo "  • To enable on_disk_payload on existing collection, patch via REST:"
	@echo "      curl -X PATCH http://localhost:6333/collections/gdrive_documents_bge \\"
	@echo "           -H 'Content-Type: application/json' \\"
	@echo "           -d '{\"on_disk_payload\": true}'"
	@echo "  • Monitor volume size: docker system df -v | grep qdrant"
	@echo "$(GREEN)✓ Qdrant cleanup complete$(NC)"

# =============================================================================
# DOCKER IMAGE DRIFT (#322)
# =============================================================================

.PHONY: verify-compose-images verify-compose-images-json verify-compose-runtime

verify-compose-images: ## Check running containers match compose-pinned images and published ports
	@python3 scripts/check_image_drift.py -f compose.yml -f compose.dev.yml --fix

verify-compose-images-json: ## Check image/port drift (JSON output for CI)
	@python3 scripts/check_image_drift.py -f compose.yml -f compose.dev.yml --json

verify-compose-runtime: verify-compose-images ## Alias: read-only local runtime drift guard (#2182/#2188)

# =============================================================================
# GIT HYGIENE
# =============================================================================

git-hygiene: ## Git hygiene report (merged branches, stale worktrees, transient files)
	@echo "$(BLUE)Running git hygiene report...$(NC)"
	@BASE_BRANCH=$${REPO_BASE_BRANCH:-dev}; \
	CURRENT_BRANCH=$$(git branch --show-current); \
	echo "Base branch: $$BASE_BRANCH"; \
	git fetch --prune origin; \
	echo ""; \
	echo "Merged local branches:"; \
	git branch --merged "origin/$$BASE_BRANCH" --format='%(refname:short)' | awk -v base="$$BASE_BRANCH" -v current="$$CURRENT_BRANCH" '$$0 != base && $$0 != "main" && $$0 != "master" && $$0 != "develop" && $$0 != current {print "  - " $$0}'; \
	echo ""; \
	echo "Branches without upstream:"; \
	git for-each-ref --format='%(refname:short) %(upstream:short)' refs/heads | awk 'NF == 1 {print "  - " $$1}'; \
	echo ""; \
	echo "Worktrees:"; \
	git worktree list --porcelain; \
	echo ""; \
	echo "Transient untracked files:"; \
	git ls-files --others --exclude-standard -- coverage.json 'test_output*' '*.log' | sed 's/^/  - /'
	@echo ""

git-hygiene-fix: ## Git hygiene safe cleanup preview (dry-run)
	@echo "$(BLUE)Running git hygiene cleanup (dry-run)...$(NC)"
	@BASE_BRANCH=$${REPO_BASE_BRANCH:-dev}; \
	CURRENT_BRANCH=$$(git branch --show-current); \
	BASE_REF=origin/$$BASE_BRANCH; \
	echo "Would delete local branches merged into $$BASE_REF, excluding protected/current branches:"; \
	git fetch --prune origin; \
	git branch --merged "$$BASE_REF" --format='%(refname:short)' | awk -v base="$$BASE_BRANCH" -v base_ref="$$BASE_REF" -v current="$$CURRENT_BRANCH" '$$0 != base && $$0 != "main" && $$0 != "master" && $$0 != "develop" && $$0 != current {print "  - git merge-base --is-ancestor " $$0 " " base_ref " && git branch -D " $$0}'
	@echo ""

pr-hygiene: ## PR queue triage report (open PRs, blocked reasons, SLA)
	@echo "$(BLUE)Running PR queue triage...$(NC)"
	uv run python scripts/pr_queue_audit.py || true
	@echo ""

issue-hygiene: ## Issue queue hygiene report (no-label / no-assignee / no-lane / stale)
	@echo "$(BLUE)Running issue queue hygiene audit...$(NC)"
	uv run python scripts/issue_queue_audit.py || true
	@echo ""

repo-cleanup: ## Full repo cleanup: branches, worktrees, stashes (dry-run)
	@echo "$(BLUE)Running repo cleanup (dry-run)...$(NC)"
	@MAIN_BRANCH=$${MAIN_BRANCH:-dev}; \
	BASE_REF=origin/$$MAIN_BRANCH; \
	CURRENT_BRANCH=$$(git branch --show-current); \
	WORKTREE_BRANCHES=$$(git worktree list --porcelain | sed -n 's/^branch refs\/heads\///p'); \
	echo "Base branch: $$MAIN_BRANCH"; \
	echo "Base ref: $$BASE_REF"; \
	git fetch --prune origin; \
	git rev-parse --verify --quiet "$$BASE_REF" >/dev/null || { echo "Missing base ref: $$BASE_REF"; exit 1; }; \
	echo ""; \
	echo "Local merged branches eligible for deletion:"; \
	git branch --merged "$$BASE_REF" --format='%(refname:short)' | while read -r branch; do \
		[ -z "$$branch" ] && continue; \
		[ "$$branch" = "$$MAIN_BRANCH" ] && continue; \
		[ "$$branch" = "main" ] && continue; \
		[ "$$branch" = "master" ] && continue; \
		[ "$$branch" = "develop" ] && continue; \
		[ "$$branch" = "$$CURRENT_BRANCH" ] && continue; \
		printf '%s\n' "$$WORKTREE_BRANCHES" | grep -Fxq "$$branch" && continue; \
		echo "  - $$branch"; \
	done; \
	echo ""; \
	echo "Remote merged branches and open PR status:"; \
	git branch -r --merged "origin/$$MAIN_BRANCH" --format='%(refname:short)' | sed 's|^origin/||' | while read -r branch; do \
		[ -z "$$branch" ] && continue; \
		[ "$$branch" = "$$MAIN_BRANCH" ] && continue; \
		[ "$$branch" = "main" ] && continue; \
		[ "$$branch" = "master" ] && continue; \
		[ "$$branch" = "develop" ] && continue; \
		if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then \
			open_prs=$$(gh pr list --head "$$branch" --state open --json number --jq length 2>/dev/null || echo unknown); \
			echo "  - $$branch (open_prs=$$open_prs)"; \
		else \
			echo "  - $$branch (gh auth unavailable; review PR status manually)"; \
		fi; \
	done; \
	echo ""; \
	echo "Worktree prune preview:"; \
	git worktree prune --dry-run; \
	echo ""; \
	echo "Stashes:"; \
	git stash list
	@echo ""

repo-cleanup-force: ## Full repo cleanup: interactive deletion mode
	@echo "$(BLUE)Running repo cleanup (interactive)...$(NC)"
	@MAIN_BRANCH=$${MAIN_BRANCH:-dev}; \
	BASE_REF=origin/$$MAIN_BRANCH; \
	CURRENT_BRANCH=$$(git branch --show-current); \
	WORKTREE_BRANCHES=$$(git worktree list --porcelain | sed -n 's/^branch refs\/heads\///p'); \
	git fetch --prune origin; \
	git rev-parse --verify --quiet "$$BASE_REF" >/dev/null || { echo "Missing base ref: $$BASE_REF"; exit 1; }; \
	echo "Local merged branches eligible for deletion from $$BASE_REF:"; \
	branches=$$(git branch --merged "$$BASE_REF" --format='%(refname:short)' | while read -r branch; do \
		[ -z "$$branch" ] && continue; \
		[ "$$branch" = "$$MAIN_BRANCH" ] && continue; \
		[ "$$branch" = "main" ] && continue; \
		[ "$$branch" = "master" ] && continue; \
		[ "$$branch" = "develop" ] && continue; \
		[ "$$branch" = "$$CURRENT_BRANCH" ] && continue; \
		printf '%s\n' "$$WORKTREE_BRANCHES" | grep -Fxq "$$branch" && continue; \
		echo "$$branch"; \
	done); \
	if [ -z "$$branches" ]; then \
		echo "  (none)"; \
	else \
		printf '%s\n' "$$branches" | sed 's/^/  - /'; \
		printf 'Delete these local branches? [y/N] '; \
		read -r confirm; \
		if printf '%s' "$$confirm" | grep -Eq '^[Yy]$$'; then \
			printf '%s\n' "$$branches" | while read -r branch; do \
				[ -z "$$branch" ] && continue; \
				if git merge-base --is-ancestor "$$branch" "$$BASE_REF"; then \
					git branch -D "$$branch"; \
				else \
					echo "  skip $$branch: not an ancestor of $$BASE_REF"; \
				fi; \
			done; \
		fi; \
	fi; \
	echo ""; \
	echo "Pruning stale worktree administrative records..."; \
	git worktree prune; \
	echo "Dirty or active worktrees are not removed by this target."
	@echo ""
