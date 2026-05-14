.PHONY: help install install-dev install-all lint format type-check security test test-full test-cov clean all-checks \
	test-preflight test-smoke test-load-eviction \
	smoke-fast smoke-zoo \
	monitoring-up monitoring-down monitoring-logs monitoring-status monitoring-test-alert \
	rclone-install sync-drive-install sync-drive-run sync-drive-status \
	ingest-dir ingest-status ingest-services \
	ingest-unified-preflight ingest-unified-bootstrap ingest-unified ingest-unified-watch ingest-unified-status ingest-unified-reprocess ingest-unified-logs \
	lock update update-pkg reinstall setup-hooks \
	qdrant-backup \
	git-hygiene git-hygiene-fix repo-cleanup repo-cleanup-force \
	docker-clean docker-clean-aggressive
	test-contract \
	docs-check \
	remote-docker-status remote-compose-config remote-docker-ps remote-env-sync remote-env-check \
	remote-active-up remote-full-up remote-bot-up remote-bot-restart remote-bot-logs \
	remote-local-up remote-local-down remote-local-logs remote-service-health

# Configurable container names & thresholds
REDIS_CONTAINER ?= dev_redis_1
EXPECTED_MAXMEMORY_SAMPLES ?= 10
PROJECT_VERSION := $(shell sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n 1)
K3S_IMAGE_REGISTRY ?= ghcr.io/yastman
K3S_IMAGE_TAG ?= v$(PROJECT_VERSION)

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
PYTEST_PARALLEL_ARGS ?= -n auto --dist=worksteal
PYTEST_FULL_PARALLEL_DIRS ?= tests/baseline/ tests/benchmark/ tests/chaos/ tests/contract/ tests/unit/
PYTEST_FULL_SEQUENTIAL_DIRS ?= tests/e2e/ tests/integration/ tests/load/ tests/smoke/
PYTEST_REQUIRES_EXTRAS_IGNORE := $(addprefix --ignore=, \
	tests/unit/test_document_parser.py \
	tests/unit/test_evaluator.py \
	tests/unit/evaluation/test_ragas_evaluation.py \
	tests/unit/voice/test_sip_setup.py \
	tests/unit/voice/test_voice_agent.py \
	tests/unit/ingestion/test_cocoindex_init.py \
	tests/unit/ingestion/test_qdrant_hybrid_target.py \
	tests/unit/ingestion/test_qdrant_hybrid_target_helpers.py \
	tests/unit/ingestion/test_qdrant_hybrid_target_state_paths.py \
	tests/unit/ingestion/test_target_sync_execution.py \
	tests/unit/ingestion/test_unified_cli.py \
	tests/unit/ingestion/test_unified_flow.py \
	tests/unit/ingestion/test_unified_flow_wiring.py)

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

local-pre-push: ## Fast local pre-push sanity gate (check + compose validate)
	@echo "$(BLUE)Running fast local pre-push sanity gate...$(NC)"
	./scripts/local_pre_push.sh
	@echo "$(GREEN)✓ Fast local pre-push sanity gate passed$(NC)"

local-pr-ready: ## Full PR readiness gate (fast gate + unit tests) - run manually
	@echo "$(BLUE)Running full PR readiness gate...$(NC)"
	./scripts/local_pre_push.sh
	@echo "$(BLUE)Running core unit tests...$(NC)"
	make test-unit
	@echo "$(GREEN)✓ Full PR readiness gate passed$(NC)"

# =============================================================================
# CODE QUALITY CHECKS
# =============================================================================

lint: ## Run Ruff linter (fast)
	@echo "$(BLUE)Running Ruff linter...$(NC)"
	uv run ruff check src/
	@echo "$(GREEN)✓ Ruff check complete$(NC)"

lint-fix: ## Run Ruff linter with auto-fix
	@echo "$(BLUE)Running Ruff with auto-fix...$(NC)"
	uv run ruff check src/ --fix
	@echo "$(GREEN)✓ Ruff auto-fix complete$(NC)"

format: ## Format code with Ruff
	@echo "$(BLUE)Formatting code with Ruff...$(NC)"
	uv run ruff format src/
	@echo "$(GREEN)✓ Code formatted$(NC)"

format-check: ## Check if code is formatted
	@echo "$(BLUE)Checking code format...$(NC)"
	uv run ruff format src/ --check
	@echo "$(GREEN)✓ Format check complete$(NC)"

type-check: ## Run MyPy type checking
	@echo "$(BLUE)Running MyPy type checking...$(NC)"
	uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary
	@echo "$(GREEN)✓ Type check complete$(NC)"

pylint: ## Run Pylint (comprehensive linting)
	@echo "$(BLUE)Running Pylint...$(NC)"
	uv run pylint src/ --rcfile=pyproject.toml || true
	@echo "$(GREEN)✓ Pylint check complete$(NC)"

security: ## Run Bandit security scan + Vulture dead-code check
	@echo "$(BLUE)Running Bandit security checks...$(NC)"
	uv run bandit -r src/ telegram_bot/ -c pyproject.toml
	@echo "$(GREEN)✓ Bandit security check complete$(NC)"
	@echo "$(BLUE)Checking for dead code with Vulture...$(NC)"
	uv run vulture src/ telegram_bot/ --min-confidence 80 --exclude "*site-packages*,*dist-info*,__pycache__,.pytest_cache,.ruff_cache,.mypy_cache,*.egg-info,.venv*"
	@echo "$(GREEN)✓ Vulture dead-code check complete$(NC)"

dead-code: ## Find dead code with Vulture (alias for security)
	@echo "$(BLUE)Checking for dead code...$(NC)"
	uv run vulture src/ telegram_bot/ --min-confidence 80 --exclude "*site-packages*,*dist-info*,__pycache__,.pytest_cache,.ruff_cache,.mypy_cache,*.egg-info,.venv*"
	@echo "$(GREEN)✓ Dead code check complete$(NC)"

all-checks: lint type-check security ## Run all code quality checks
	@echo "$(GREEN)✓✓✓ All checks passed! ✓✓✓$(NC)"

# =============================================================================
# TESTING
# =============================================================================

test: ## Run fast deterministic PR/local gate (unit + critical graph paths)
	@echo "$(BLUE)Running fast test gate (unit + graph_paths)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ tests/integration/test_graph_paths.py -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api and not requires_extras"
	@echo "$(GREEN)✓ Fast test gate complete$(NC)"

test-full: ## Run full test suite with hybrid parallelism (all tiers)
	@echo "$(BLUE)Running full test suite...$(NC)"
	uv sync --all-extras --all-groups
	@echo "$(BLUE)Phase 1/2: parallel-safe suites...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_FULL_PARALLEL_DIRS) $(PYTEST_PARALLEL_ARGS) --timeout=30 $(PYTEST_ADDOPTS)
	@echo "$(BLUE)Phase 2/2: stateful/live suites sequentially...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest $(PYTEST_FULL_SEQUENTIAL_DIRS) --timeout=30 $(PYTEST_ADDOPTS)
	@echo "$(GREEN)✓ Full test suite complete$(NC)"

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest tests/ --cov=src --cov=telegram_bot --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ## Run core unit tests locally in parallel (fast default gate)
	@echo "$(BLUE)Running core unit tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Core unit tests complete$(NC)"

test-unit-loadscope: ## Run unit tests with loadscope (faster fixture reuse locally)
	@echo "$(BLUE)Running unit tests (loadscope)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ $(PYTEST_REQUIRES_EXTRAS_IGNORE) -n auto --dist=loadscope -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Unit tests (loadscope) complete$(NC)"

test-unit-full: ## Run all unit tests including optional-dep tests (nightly/main)
	@echo "$(BLUE)Running full unit tests (all extras)...$(NC)"
	uv sync --extra voice --extra ingest --extra eval --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)✓ Full unit tests complete$(NC)"

test-unit-extras: ## Run optional-extra unit tests only
	@echo "$(BLUE)Running optional-extra unit tests...$(NC)"
	uv sync --extra voice --extra ingest --extra eval --all-groups
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "requires_extras"
	@echo "$(GREEN)✓ Optional-extra unit tests complete$(NC)"

test-contract: ## Run trace contract tests (static analysis, no Docker)
	@echo "$(BLUE)Running trace contract tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/contract/ -n auto --dist=worksteal -q --timeout=30
	@echo "$(GREEN)Trace contract tests complete$(NC)"

test-fast: ## Run unit tests in parallel (xdist, loadscope)
	@echo "$(BLUE)Running unit tests in parallel...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)✓ Parallel tests complete$(NC)"

test-all-fast: ## Run ALL test suites in parallel (unit + integration + smoke)
	@echo "$(BLUE)Running all tests in parallel...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ tests/integration/test_graph_paths.py -n auto -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)✓ All fast tests complete$(NC)"

test-lf: ## Run only last failed tests (parallel)
	@echo "$(BLUE)Running last failed tests...$(NC)"
	uv run pytest tests/unit/ --lf -n auto -q
	@echo "$(GREEN)✓ Last failed tests complete$(NC)"

test-ff: ## Run failed first, then rest
	@echo "$(BLUE)Running failed first...$(NC)"
	uv run pytest tests/unit/ --ff -v
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-profile: ## Profile slowest tests (find bottlenecks)
	@echo "$(BLUE)Profiling slow tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ --durations=20 --durations-min=0.5 -n auto -q
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
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ --store-durations -n auto --timeout=30 -m "not legacy_api" -q
	@echo "$(GREEN)✓ .test_durations updated — commit this file$(NC)"

test-all: ## Run all tests with coverage threshold (CI mode)
	@echo "$(BLUE)Running all tests with coverage...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/ -v -n auto --cov=src --cov=telegram_bot --cov-report=term-missing --cov-fail-under=80
	@echo "$(GREEN)✓ All tests passed with 80%+ coverage$(NC)"

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

.PHONY: test-bot-health test-bot-health-vps

test-bot-health: ## Preflight: verify local native-bot prerequisites (Redis/Qdrant/LiteLLM + optional Postgres note)
	@echo "$(BLUE)Running bot health preflight...$(NC)"
	@./scripts/test_bot_health.sh
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
	urllib.request.urlopen('http://litellm:4000/health/liveliness', timeout=10); \
	print('  ✓ LiteLLM OK'); \
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

# =============================================================================
# DOCKER PROFILES
# =============================================================================

# Common compose command with --compatibility to enforce deploy.resources.limits
COMPOSE_CMD := docker compose --compatibility
LOCAL_COMPOSE_FILE := compose.yml:compose.dev.yml
# Local dev env fallback: use .env if present, otherwise safe CI fixture values
LOCAL_COMPOSE_CMD := COMPOSE_FILE=$(LOCAL_COMPOSE_FILE) $(COMPOSE_CMD) --env-file $$( [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env )
# Runtime env for E2E trace gates: allow worktrees to point at the main checkout .env
RAG_RUNTIME_ENV_FILE ?= $$( [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env )
export RAG_RUNTIME_ENV_FILE

# =============================================================================
# REMOTE MACBOOK DOCKER HOST
# =============================================================================

REMOTE_DOCKER_HOST ?= macbook-docker
REMOTE_DOCKER_IP ?= 192.168.31.168
REMOTE_DOCKER_REPO ?= /Users/aroslav/Documents/rag-fresh
REMOTE_DOCKER_PATH ?= /opt/homebrew/bin:/usr/local/bin
REMOTE_COMPOSE_FILE ?= compose.yml:compose.dev.yml
REMOTE_BGE_M3_MEMORY_LIMIT ?= 6G
REMOTE_SSH := ssh $(REMOTE_DOCKER_HOST)

REMOTE_ACTIVE_SERVICES := mini-app-frontend mini-app-api bge-m3 litellm redis langfuse langfuse-worker postgres redis-langfuse qdrant rag-api minio clickhouse user-base bot

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
		if ! grep -qE '^TELEGRAM_BOT_TOKEN=' .env; then missing=\"$$missing TELEGRAM_BOT_TOKEN\"; fi; \
		if ! grep -qE '^LITELLM_MASTER_KEY=' .env; then missing=\"$$missing LITELLM_MASTER_KEY\"; fi; \
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

remote-active-up: ## Start active remote stack (bot + ml + voice profiles)
	@echo "$(BLUE)Starting active remote stack on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile bot --profile ml --profile voice up -d $(REMOTE_ACTIVE_SERVICES)"
	@echo "$(GREEN)✓ Active remote stack started$(NC)"

remote-full-up: ## Start full remote stack (all profiles)
	@echo "$(BLUE)Starting full remote stack on $(REMOTE_DOCKER_HOST)...$(NC)"
	@$(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_BAKE=true && export BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT) && COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` --profile full up -d"
	@echo "$(GREEN)✓ Full remote stack started$(NC)"

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

remote-service-health: ## Check remote service health over SSH on 127.0.0.1
	@echo "$(BLUE)Remote service health ($(REMOTE_DOCKER_HOST))...$(NC)"
	@fail=0; \
	if ! $(REMOTE_SSH) "curl -fsS http://127.0.0.1:6333/readyz >/dev/null 2>&1"; then echo "  Qdrant: $(RED)FAIL$(NC)"; fail=1; else echo "  Qdrant: $(GREEN)OK$(NC)"; fi; \
	if ! $(REMOTE_SSH) "curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1"; then echo "  BGE-M3: $(RED)FAIL$(NC)"; fail=1; else echo "  BGE-M3: $(GREEN)OK$(NC)"; fi; \
	if ! $(REMOTE_SSH) "curl -fsS http://127.0.0.1:4000/health/liveliness >/dev/null 2>&1"; then echo "  LiteLLM: $(RED)FAIL$(NC)"; fail=1; else echo "  LiteLLM: $(GREEN)OK$(NC)"; fi; \
	if $(REMOTE_SSH) "curl -fsS http://127.0.0.1:3001/api/public/health >/dev/null 2>&1"; then echo "  Langfuse: $(GREEN)OK$(NC)"; else echo "  Langfuse: $(YELLOW)NOT READY$(NC)"; fi; \
	if $(REMOTE_SSH) "curl -fsS http://127.0.0.1:5001/health >/dev/null 2>&1"; then echo "  Docling: $(GREEN)OK$(NC)"; else echo "  Docling: $(YELLOW)NOT READY$(NC)"; fi; \
	bot_restarts=$$($(REMOTE_SSH) "cd $(REMOTE_DOCKER_REPO) && export PATH=$(REMOTE_DOCKER_PATH):$$PATH && cid=\$$(COMPOSE_FILE=$(REMOTE_COMPOSE_FILE) docker compose --compatibility --env-file \`[ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env\` ps -q bot 2>/dev/null); if [ -n \"\$$cid\" ]; then docker inspect --format='{{.RestartCount}}' \$$cid 2>/dev/null; else echo N/A; fi"); \
	if [ "$$bot_restarts" != "N/A" ]; then echo "  Bot: running (restarts: $$bot_restarts)"; else echo "  Bot: $(YELLOW)container not found$(NC)"; fi; \
	exit $$fail

.PHONY: docker-core-up docker-bot-up docker-obs-up docker-ai-up docker-ingest-up docker-voice-up docker-full-up docker-down docker-ps

docker-core-up: ## Start default local compose stack (unprofiled services)
	@echo "$(BLUE)Starting core services...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d
	@echo "$(GREEN)✓ Core services started$(NC)"

docker-bot-up: ## Start core + bot services (litellm, bot)
	@echo "$(BLUE)Starting bot services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile bot up -d
	@echo "$(GREEN)✓ Bot services started$(NC)"

docker-obs-up: ## Start core + observability (loki, promtail, alertmanager)
	@echo "$(BLUE)Starting observability services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile obs up -d
	@echo "$(GREEN)✓ Observability services started$(NC)"

docker-ml-up: ## Start core + ML platform (langfuse, clickhouse, minio)
	@echo "$(BLUE)Starting ML platform services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile ml up -d
	@echo "$(GREEN)✓ ML platform started$(NC)"

docker-ai-up: ## Start core + heavy AI services (bge-m3, user-base)
	@echo "$(BLUE)Starting AI services...$(NC)"
	$(LOCAL_COMPOSE_CMD) up -d bge-m3 user-base
	@echo "$(GREEN)✓ AI services started$(NC)"

docker-ingest-up: ## Start core + ingestion service
	@echo "$(BLUE)Starting ingestion service...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile ingest up -d
	@echo "$(GREEN)✓ Ingestion service started$(NC)"

docker-voice-up: ## Start core + voice services (livekit, sip, voice-agent)
	@echo "$(BLUE)Preflight: checking livekit config...$(NC)"
	@test -f docker/livekit/livekit.yaml || { echo "$(RED)✗ docker/livekit/livekit.yaml not found$(NC)"; exit 1; }
	@echo "$(BLUE)Starting voice services...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile voice up -d
	@echo "$(GREEN)✓ Voice services started$(NC)"

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

check: lint type-check ## Quick check (lint + types)
	@echo "$(GREEN)✓ Quick check complete$(NC)"

fix: lint-fix format ## Fix all auto-fixable issues
	@echo "$(GREEN)✓ Auto-fixes applied$(NC)"

qa: all-checks test ## Full quality assurance
	@echo "$(GREEN)✓✓✓ Full QA complete! ✓✓✓$(NC)"

# =============================================================================
# Local Development (compose.yml + compose.dev.yml via COMPOSE_FILE env)
# =============================================================================

.PHONY: local-up local-up-ingest local-down local-logs local-ps local-build local-redis-recreate run-bot bot
LOCAL_SERVICES := redis qdrant bge-m3 litellm
LOCAL_INGEST_SERVICES := docling
LOCAL_ALL_SERVICES := $(LOCAL_SERVICES) $(LOCAL_INGEST_SERVICES)

local-up:  ## Start local Docker services (bot runs via make run-bot)
	$(LOCAL_COMPOSE_CMD) up -d $(LOCAL_SERVICES)
	@echo "$(GREEN)✓ Local services started. Run bot: make run-bot$(NC)"

local-up-ingest:  ## Start local services + docling for ingestion workflows
	$(LOCAL_COMPOSE_CMD) up -d $(LOCAL_ALL_SERVICES)
	@echo "$(GREEN)✓ Local services + docling started$(NC)"

run-bot:  ## Run bot locally (requires: make local-up)
	uv run --env-file .env python -m telegram_bot.main

bot:  ## Alias: run bot and tee output to logs/bot-run.log
	@mkdir -p logs
	uv run --env-file .env python -m telegram_bot.main 2>&1 | tee logs/bot-run.log; echo '[COMPLETE]'

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

deploy-bot:  ## Show official deploy flow: push dev/feature, open PR, merge to main for auto-deploy
	@echo "$(CYAN)Official deploy flow:$(NC)"
	@echo "  1. Commit locally"
	@echo "  2. Push your work branch or dev"
	@echo "  3. Open PR to main"
	@echo "  4. Merge PR into main"
	@echo "  5. GitHub Actions auto-deploys main to VPS"
	@echo "$(GREEN)No direct push to main is performed by this target.$(NC)"

deploy-vps-local:  ## Fallback/manual deploy: sync local workspace to VPS via rsync + rebuild
	@echo "$(CYAN)Deploying local workspace to VPS via fallback rsync flow...$(NC)"
	./scripts/deploy-vps.sh
	@echo "$(GREEN)✓ Deploy complete$(NC)"

# =============================================================================
# E2E TESTING
# =============================================================================

.PHONY: e2e-install e2e-generate-data e2e-index-data e2e-test e2e-test-traces e2e-test-traces-core e2e-test-group e2e-telegram-test e2e-setup langfuse-latest-trace-audit

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

e2e-telegram-test: ## Run Telegram userbot E2E runner (Telethon + judge)
	@echo "$(BLUE)Running Telegram E2E runner...$(NC)"
	uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py
	@echo "$(GREEN)✓ Telegram E2E runner complete$(NC)"

e2e-test-traces: ## Run E2E tests + validate Langfuse traces
	@echo "$(BLUE)Running E2E tests with Langfuse trace validation...$(NC)"
	E2E_VALIDATE_LANGFUSE=1 uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py
	@echo "$(GREEN)✓ E2E tests with trace validation complete$(NC)"

e2e-test-traces-core: ## Run required #1307 Telethon scenarios with Langfuse validation
	@echo "$(BLUE)Running #1307 core Telethon trace scenarios...$(NC)"
	E2E_VALIDATE_LANGFUSE=1 uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1 --scenario 8.1
	@echo "$(GREEN)✓ #1307 core trace scenarios complete$(NC)"

e2e-test-group: ## Run specific test group (usage: make e2e-test-group GROUP=filters)
	uv run python scripts/e2e/runner.py --group $(GROUP)

e2e-setup: e2e-install ## Full E2E setup on canonical collection
	@echo "$(YELLOW)Using canonical collection via E2E_COLLECTION_NAME (default: gdrive_documents_bge)$(NC)"
	@echo "$(GREEN)✓ E2E setup complete$(NC)"

langfuse-latest-trace-audit: ## Sanitized post-E2E Langfuse latest-trace audit
	@echo "$(BLUE)Running sanitized latest-trace audit...$(NC)"
	uv run python scripts/e2e/langfuse_latest_trace_audit.py --limit 20
	@echo "$(GREEN)✓ Latest-trace audit complete$(NC)"

# =============================================================================
# BASELINE & OBSERVABILITY
# =============================================================================

.PHONY: baseline-smoke baseline-load baseline-compare baseline-set baseline-report baseline-check

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

baseline-check: baseline-smoke ## Quick baseline check (smoke + compare with main)
	@echo "$(BLUE)Comparing with main baseline...$(NC)"
	make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=$(BASELINE_SESSION)

# =============================================================================
# RAG EVALUATION (RAGAS + DeepEval)
# =============================================================================

.PHONY: eval-rag eval-rag-quick eval-rag-full

eval-rag: ## Run RAG evaluation with RAGAS metrics (faithfulness >= 0.8)
	@echo "$(BLUE)Running RAG evaluation with RAGAS...$(NC)"
	@echo "$(YELLOW)Dataset: tests/eval/ground_truth.json (55 samples)$(NC)"
	@echo "$(YELLOW)LLM: $(EVAL_MODEL) via $(LITELLM_BASE_URL)$(NC)"
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
# MONITORING & ALERTING
# =============================================================================

.PHONY: monitoring-up monitoring-down monitoring-logs monitoring-status monitoring-test-alert

monitoring-up: ## Start monitoring stack (Loki, Promtail, Alertmanager)
	@echo "$(BLUE)Starting monitoring stack...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile obs up -d
	@echo "$(GREEN)✓ Monitoring stack started$(NC)"
	@echo "$(YELLOW)Services:$(NC)"
	@echo "  Loki:         http://localhost:3100"
	@echo "  Alertmanager: http://localhost:9093"

monitoring-down: ## Stop monitoring stack
	@echo "$(BLUE)Stopping monitoring stack...$(NC)"
	$(LOCAL_COMPOSE_CMD) --profile obs stop
	@echo "$(GREEN)✓ Monitoring stack stopped$(NC)"

monitoring-logs: ## View monitoring stack logs
	@echo "$(BLUE)Monitoring stack logs (Ctrl+C to exit):$(NC)"
	$(LOCAL_COMPOSE_CMD) logs -f loki promtail alertmanager

monitoring-status: ## Show monitoring stack status
	@echo "$(BLUE)Monitoring stack status:$(NC)"
	@$(LOCAL_COMPOSE_CMD) ps loki promtail alertmanager
	@echo ""
	@echo "$(YELLOW)Checking health...$(NC)"
	@curl -s http://localhost:3100/ready > /dev/null 2>&1 && echo "  Loki: $(GREEN)OK$(NC)" || echo "  Loki: $(RED)DOWN$(NC)"
	@curl -s http://localhost:9093/-/healthy > /dev/null 2>&1 && echo "  Alertmanager: $(GREEN)OK$(NC)" || echo "  Alertmanager: $(RED)DOWN$(NC)"
	@docker logs dev-promtail 2>&1 | tail -1 | grep -q "level=info" && echo "  Promtail: $(GREEN)OK$(NC)" || echo "  Promtail: $(YELLOW)CHECK LOGS$(NC)"

monitoring-test-alert: ## Send a test alert to verify Telegram integration
	@echo "$(BLUE)Sending test alert...$(NC)"
	@# Load the canonical local .env file so `make` works without manual `source`.
	@set -a; [ -f ./.env ] && . ./.env; set +a; \
	if [ -z "$$TELEGRAM_ALERTING_BOT_TOKEN" ] || [ -z "$$TELEGRAM_ALERTING_CHAT_ID" ]; then \
		echo "$(RED)Error: TELEGRAM_ALERTING_BOT_TOKEN and TELEGRAM_ALERTING_CHAT_ID must be set$(NC)"; \
		echo "$(YELLOW)Export them or add to .env file$(NC)"; \
		exit 1; \
	fi
	@START_AT=$$(date -u -Iseconds); \
	END_AT=$$(date -u -Iseconds -d '+2 minutes'); \
	curl -fsS -X POST http://localhost:9093/api/v2/alerts \
		-H "Content-Type: application/json" \
		-d "[{\"labels\":{\"alertname\":\"TestAlert\",\"severity\":\"critical\",\"service\":\"test\"},\"annotations\":{\"summary\":\"Test alert from make monitoring-test-alert\",\"description\":\"This is a test alert to verify Telegram integration is working correctly.\"},\"startsAt\":\"$$START_AT\",\"endsAt\":\"$$END_AT\"}]" \
		> /dev/null && echo "$(GREEN)✓ Test alert sent! Check your Telegram.$(NC)" || echo "$(RED)Failed to send alert. Is Alertmanager running?$(NC)"

# =============================================================================
# GOOGLE DRIVE SYNC (rclone)
# =============================================================================

.PHONY: rclone-install sync-drive-install sync-drive-run sync-drive-status

rclone-install: ## Install rclone
	@echo "$(BLUE)Installing rclone...$(NC)"
	curl https://rclone.org/install.sh | sudo bash
	@echo "$(GREEN)✓ rclone installed$(NC)"

sync-drive-install: ## Install rclone cron job
	@echo "$(BLUE)Installing rclone cron...$(NC)"
	@$(ENV_LOAD) \
	: "$${GDRIVE_SYNC_DIR:?GDRIVE_SYNC_DIR is required}"; \
	: "$${RCLONE_CONFIG_FILE:?RCLONE_CONFIG_FILE is required}"; \
	test -f "$${RCLONE_CONFIG_FILE}" || { echo "$(RED)Error: RCLONE_CONFIG_FILE not found at $${RCLONE_CONFIG_FILE}$(NC)"; exit 1; }; \
	sudo mkdir -p /opt/scripts /opt/credentials /etc/rag-fresh "$${GDRIVE_SYNC_DIR}"; \
	sudo cp docker/rclone/sync-drive.sh /opt/scripts/; \
	sudo cp docker/rclone/gdrive-manifest.sh /opt/scripts/; \
	sudo chmod +x /opt/scripts/sync-drive.sh /opt/scripts/gdrive-manifest.sh; \
	printf 'GDRIVE_SYNC_DIR=%s\nRCLONE_CONFIG_FILE=%s\nRCLONE_REMOTE=%s\n' \
	  "$${GDRIVE_SYNC_DIR}" "$${RCLONE_CONFIG_FILE}" "$${RCLONE_REMOTE:-gdrive:RAG}" | \
	  sudo tee /etc/rag-fresh/rclone-sync.env >/dev/null; \
	sudo chmod 600 /etc/rag-fresh/rclone-sync.env; \
	sudo cp docker/rclone/crontab /etc/cron.d/rclone-sync; \
	sudo chmod 644 /etc/cron.d/rclone-sync
	@echo "$(GREEN)✓ Cron installed$(NC)"

sync-drive-run: ## Run Drive sync manually
	@echo "$(BLUE)Syncing Google Drive...$(NC)"
	@$(ENV_LOAD) \
	: "$${GDRIVE_SYNC_DIR:?GDRIVE_SYNC_DIR is required}"; \
	: "$${RCLONE_CONFIG_FILE:?RCLONE_CONFIG_FILE is required}"; \
	test -f "$${RCLONE_CONFIG_FILE}" || { echo "$(RED)Error: RCLONE_CONFIG_FILE not found at $${RCLONE_CONFIG_FILE}$(NC)"; exit 1; }; \
	/opt/scripts/sync-drive.sh
	@echo "$(GREEN)✓ Sync complete$(NC)"

sync-drive-status: ## Show sync status and recent files
	@echo "$(BLUE)Recent synced files:$(NC)"
	@$(ENV_LOAD) \
	if [ -n "$${GDRIVE_SYNC_DIR:-}" ] && [ -d "$${GDRIVE_SYNC_DIR}" ]; then \
	  ls -lt "$${GDRIVE_SYNC_DIR}" 2>/dev/null | head -20; \
	else \
	  echo "No files synced yet"; \
	fi
	@echo ""
	@echo "$(BLUE)Last sync log:$(NC)"
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

.PHONY: qdrant-backup

qdrant-backup: ## Create Qdrant collection snapshots (all collections)
	@echo "$(BLUE)Creating Qdrant snapshots...$(NC)"
	uv run python scripts/qdrant_snapshot.py
	@echo "$(GREEN)✓ Qdrant backup complete$(NC)"

# =============================================================================
# TRACE VALIDATION (#110)
# =============================================================================

.PHONY: validate-traces validate-traces-fast

# Local host defaults for native trace validation (issue #1380).
# Callers can override per-variable: make validate-traces-fast QDRANT_URL=http://custom:6333 REDIS_URL=redis://:x@custom:6379

validate-traces: ## Full rebuild + trace validation + report
	@echo "$(BLUE)Full rebuild + validation...$(NC)"
	$(LOCAL_COMPOSE_CMD) build --no-cache bot litellm bge-m3
	$(LOCAL_COMPOSE_CMD) --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)Validation complete — see docs/reports/$(NC)"

validate-traces-fast: ## No rebuild; trace validation fails if required trace families are missing
	@echo "$(BLUE)Fast validation (no rebuild)...$(NC)"
	TRACE_ENV_FILE="$$( [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env )"; \
	uv run python scripts/validate_trace_runtime.py --env-file "$$TRACE_ENV_FILE"
	$(LOCAL_COMPOSE_CMD) --profile bot --profile ml up -d --wait
	QDRANT_URL="$(or $(QDRANT_URL),http://localhost:6333)" \
	BGE_M3_URL="$(or $(BGE_M3_URL),http://localhost:8000)" \
	REDIS_URL="$(or $(REDIS_URL),redis://localhost:6379)" \
	REDIS_PASSWORD="$(or $(REDIS_PASSWORD),dev_redis_pass)" \
	LLM_BASE_URL="$(or $(LLM_BASE_URL),http://localhost:4000)" \
	LANGFUSE_HOST="$(or $(LANGFUSE_HOST),http://localhost:3001)" \
	LANGFUSE_PUBLIC_KEY="$(or $(LANGFUSE_PUBLIC_KEY),pk-lf-dev)" \
	LANGFUSE_SECRET_KEY="$(or $(LANGFUSE_SECRET_KEY),sk-lf-dev)" \
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)Validation complete — see docs/reports/$(NC)"

# =============================================================================
# K3S DEPLOYMENT
# =============================================================================

.PHONY: k3s-core k3s-bot k3s-ingest k3s-full k3s-status k3s-logs k3s-down k3s-secrets k3s-ingest-start k3s-ingest-stop \
	k3s-build k3s-build-bot k3s-build-ingest k3s-push-all k3s-prepull

k3s-core: ## Deploy core services (postgres, redis, qdrant) to k3s
	kubectl apply -k k8s/overlays/core/ --load-restrictor=LoadRestrictionsNone

k3s-bot: ## Deploy bot stack to k3s (core + ML + litellm + bot)
	kubectl apply -k k8s/overlays/bot/ --load-restrictor=LoadRestrictionsNone

k3s-ingest: ## Deploy ingestion stack to k3s (core + docling + bge-m3 + ingestion)
	kubectl apply -k k8s/overlays/ingest/ --load-restrictor=LoadRestrictionsNone

k3s-full: ## Deploy all services to k3s
	kubectl apply -k k8s/overlays/full/

k3s-status: ## Show k3s pod status
	kubectl get pods -n rag -o wide

k3s-logs: ## Show logs for a service: make k3s-logs SVC=bot
	kubectl logs -n rag deployment/$(SVC) -f --tail=50

k3s-down: ## Delete all k3s resources
	kubectl delete -k k8s/overlays/full/ --ignore-not-found

k3s-secrets: ## Create k8s secrets from k8s/secrets/.env
	@tmp_api_keys=$$(mktemp); \
		tmp_db_credentials=$$(mktemp); \
		trap 'rm -f "$$tmp_api_keys" "$$tmp_db_credentials"' EXIT; \
		grep -v '^POSTGRES_PASSWORD=' k8s/secrets/.env > "$$tmp_api_keys"; \
		POSTGRES_PASSWORD=$$(awk -F= '/^POSTGRES_PASSWORD=/{sub(/^[^=]*=/,""); print; found=1; exit} END{if(!found) exit 1}' k8s/secrets/.env) || { \
			echo "POSTGRES_PASSWORD is required in k8s/secrets/.env" >&2; \
			exit 1; \
		}; \
		[ -n "$$POSTGRES_PASSWORD" ] || { \
			echo "POSTGRES_PASSWORD is required in k8s/secrets/.env" >&2; \
			exit 1; \
		}; \
		printf 'POSTGRES_USER=postgres\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=postgres\n' "$$POSTGRES_PASSWORD" > "$$tmp_db_credentials"; \
		kubectl create secret generic api-keys --from-env-file="$$tmp_api_keys" -n rag --dry-run=client -o yaml | kubectl apply -f -; \
		kubectl create secret generic db-credentials --from-env-file="$$tmp_db_credentials" -n rag --dry-run=client -o yaml | kubectl apply -f -

k3s-ingest-start: ## Scale ingestion to 1 replica
	kubectl scale deployment ingestion -n rag --replicas=1

k3s-ingest-stop: ## Scale ingestion to 0 replicas
	kubectl scale deployment ingestion -n rag --replicas=0

k3s-push-%: ## Build and push a versioned GHCR image: make k3s-push-bot K3S_IMAGE_TAG=v2.14.0
	@case "$*" in \
		bot) dockerfile="telegram_bot/Dockerfile"; build_context="."; image_name="rag-bot" ;; \
		ingestion) dockerfile="Dockerfile.ingestion"; build_context="."; image_name="rag-ingestion" ;; \
		docling) dockerfile="services/docling/Dockerfile"; build_context="./services/docling"; image_name="rag-docling" ;; \
		user-base) dockerfile="services/user-base/Dockerfile"; build_context="./services/user-base"; image_name="rag-user-base" ;; \
		bge-m3) dockerfile="services/bge-m3-api/Dockerfile"; build_context="./services/bge-m3-api"; image_name="rag-bge-m3" ;; \
		*) echo "Unsupported k3s image target: $*"; exit 1 ;; \
	esac; \
	image_ref="$(K3S_IMAGE_REGISTRY)/$$image_name:$(K3S_IMAGE_TAG)"; \
	echo "Building $$image_ref from $$dockerfile (context $$build_context)"; \
	docker build -f "$$dockerfile" -t "$$image_ref" "$$build_context"; \
	docker push "$$image_ref"

# =============================================================================
# DOCKER IMAGE DRIFT (#322)
# =============================================================================

.PHONY: verify-compose-images verify-compose-images-json

verify-compose-images: ## Check running containers match compose-pinned images
	@uv run python scripts/check_image_drift.py -f compose.yml -f compose.dev.yml --fix

verify-compose-images-json: ## Check image drift (JSON output for CI)
	@uv run python scripts/check_image_drift.py -f compose.yml -f compose.dev.yml --json

# =============================================================================
# GIT HYGIENE
# =============================================================================

git-hygiene: ## Git hygiene report (merged branches, stale worktrees, transient files)
	@echo "$(BLUE)Running git hygiene report...$(NC)"
	uv run python scripts/git_hygiene.py || true
	@echo ""

git-hygiene-fix: ## Git hygiene safe cleanup preview (dry-run)
	@echo "$(BLUE)Running git hygiene cleanup (dry-run)...$(NC)"
	uv run python scripts/git_hygiene.py --fix --dry-run || true
	@echo ""

repo-cleanup: ## Full repo cleanup: branches, worktrees, stashes (dry-run)
	@echo "$(BLUE)Running repo cleanup (dry-run)...$(NC)"
	bash scripts/repo_cleanup.sh --dry-run
	@echo ""

repo-cleanup-force: ## Full repo cleanup: interactive deletion mode
	@echo "$(BLUE)Running repo cleanup (interactive)...$(NC)"
	bash scripts/repo_cleanup.sh --force
	@echo ""
