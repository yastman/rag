.PHONY: help install install-dev install-all lint format type-check security test test-full test-cov clean all-checks \
	test-preflight test-smoke test-smoke-routing test-load test-load-ci test-load-eviction \
	test-load-update-baseline test-all-smoke-load smoke-fast smoke-zoo \
	monitoring-up monitoring-down monitoring-logs monitoring-status monitoring-test-alert \
	rclone-install sync-drive-install sync-drive-run sync-drive-status \
	ingest-dir ingest-gdrive ingest-status ingest-services \
	ingest-gdrive-setup ingest-gdrive-run ingest-gdrive-watch ingest-gdrive-status \
	ingest-unified ingest-unified-watch ingest-unified-status ingest-unified-reprocess ingest-unified-logs \
	lock update update-pkg reinstall setup-hooks \
	qdrant-backup \
	git-hygiene git-hygiene-fix repo-cleanup repo-cleanup-force \
	test-contract

# Configurable container names & thresholds
REDIS_CONTAINER ?= dev-redis
EXPECTED_MAXMEMORY_SAMPLES ?= 10

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Contextual RAG v2.0.1 - Development Commands$(NC)"
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
	uv run mypy src/ --ignore-missing-imports
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
	uv run vulture src/ telegram_bot/ --min-confidence 80
	@echo "$(GREEN)✓ Vulture dead-code check complete$(NC)"

dead-code: ## Find dead code with Vulture (alias for security)
	@echo "$(BLUE)Checking for dead code...$(NC)"
	uv run vulture src/ telegram_bot/ --min-confidence 80
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

test-full: ## Run full test suite (all tiers)
	@echo "$(BLUE)Running full test suite...$(NC)"
	uv sync --all-extras --all-groups
	uv run pytest tests/
	@echo "$(GREEN)✓ Full test suite complete$(NC)"

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest tests/ --cov=src --cov=telegram_bot --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ## Run core unit tests locally in parallel (fast default gate)
	@echo "$(BLUE)Running core unit tests...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Core unit tests complete$(NC)"

test-unit-loadscope: ## Run unit tests with loadscope (faster fixture reuse locally)
	@echo "$(BLUE)Running unit tests (loadscope)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=loadscope -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)✓ Unit tests (loadscope) complete$(NC)"

test-unit-core: ## Run core unit tests (no optional deps needed, PR gate)
	@echo "$(BLUE)Running core unit tests (no optional deps)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api and not requires_extras and not slow"
	@echo "$(GREEN)✓ Core unit tests complete$(NC)"

test-unit-full: ## Run all unit tests including optional-dep tests (nightly/main)
	@echo "$(BLUE)Running full unit tests (all extras)...$(NC)"
	PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/unit/ -n auto --dist=worksteal -q --timeout=30 -m "not legacy_api"
	@echo "$(GREEN)✓ Full unit tests complete$(NC)"

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

test-smoke-routing: ## Run smoke routing tests only (no deps)
	@echo "$(BLUE)Running smoke routing tests...$(NC)"
	uv run pytest tests/smoke/test_smoke_routing.py -v
	@echo "$(GREEN)✓ Routing tests complete$(NC)"

test-load: ## Run load tests (live services)
	@echo "$(BLUE)Running load tests...$(NC)"
	uv run pytest tests/load/test_load_conversations.py -v -s
	@echo "$(GREEN)✓ Load tests complete$(NC)"

test-load-ci: ## Run load tests in CI (mocked, fast)
	@echo "$(BLUE)Running load tests (CI mode)...$(NC)"
	LOAD_USE_MOCKS=1 LOAD_CHAT_COUNT=5 uv run pytest tests/load/test_load_conversations.py -v
	@echo "$(GREEN)✓ Load tests (CI) complete$(NC)"

test-load-eviction: ## Run Redis eviction tests
	@echo "$(BLUE)Running Redis eviction tests...$(NC)"
	uv run pytest tests/load/test_load_redis_eviction.py -v -s
	@echo "$(GREEN)✓ Redis eviction tests complete$(NC)"

test-load-update-baseline: ## Update load test baseline
	@echo "$(BLUE)Updating baseline...$(NC)"
	uv run pytest tests/load/test_load_conversations.py -v --update-baseline
	@echo "$(GREEN)✓ Baseline updated$(NC)"

test-all-smoke-load: test-preflight test-smoke test-load ## Full smoke+load suite
	@echo "$(GREEN)✓✓✓ All smoke+load tests complete$(NC)"

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

test-bot-health: ## Preflight: verify Qdrant collection + LLM (local dev, ports published)
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

# =============================================================================
# DOCKER PROFILES
# =============================================================================

# Common compose command with --compatibility to enforce deploy.resources.limits
COMPOSE_CMD := docker compose --compatibility

.PHONY: docker-core-up docker-bot-up docker-obs-up docker-ml-up docker-ai-up docker-ingest-up docker-voice-up docker-full-up docker-down docker-ps

docker-core-up: ## Start core services (postgres, qdrant, redis, docling)
	@echo "$(BLUE)Starting core services...$(NC)"
	$(COMPOSE_CMD) up -d
	@echo "$(GREEN)✓ Core services started$(NC)"

docker-bot-up: ## Start core + bot services (litellm, bot)
	@echo "$(BLUE)Starting bot services...$(NC)"
	$(COMPOSE_CMD) --profile bot up -d
	@echo "$(GREEN)✓ Bot services started$(NC)"

docker-obs-up: ## Start core + observability (loki, promtail, alertmanager)
	@echo "$(BLUE)Starting observability services...$(NC)"
	$(COMPOSE_CMD) --profile obs up -d
	@echo "$(GREEN)✓ Observability services started$(NC)"

docker-ml-up: ## Start core + ML platform (langfuse, mlflow, clickhouse, minio)
	@echo "$(BLUE)Starting ML platform services...$(NC)"
	$(COMPOSE_CMD) --profile ml up -d
	@echo "$(GREEN)✓ ML platform started$(NC)"

docker-ai-up: ## Start core + heavy AI services (bge-m3, user-base)
	@echo "$(BLUE)Starting AI services...$(NC)"
	$(COMPOSE_CMD) up -d bge-m3 user-base
	@echo "$(GREEN)✓ AI services started$(NC)"

docker-ingest-up: ## Start core + ingestion service
	@echo "$(BLUE)Starting ingestion service...$(NC)"
	$(COMPOSE_CMD) --profile ingest up -d
	@echo "$(GREEN)✓ Ingestion service started$(NC)"

docker-voice-up: ## Start core + voice services (livekit, sip, voice-agent)
	@echo "$(BLUE)Preflight: checking livekit config...$(NC)"
	@test -f docker/livekit/livekit.yaml || { echo "$(RED)✗ docker/livekit/livekit.yaml not found$(NC)"; exit 1; }
	@echo "$(BLUE)Starting voice services...$(NC)"
	$(COMPOSE_CMD) --profile voice up -d
	@echo "$(GREEN)✓ Voice services started$(NC)"

docker-full-up: ## Start all services (full stack)
	@echo "$(BLUE)Starting full stack...$(NC)"
	$(COMPOSE_CMD) --profile full up -d
	@echo "$(GREEN)✓ Full stack started$(NC)"

docker-up: docker-core-up ## Alias for docker-core-up (backward compat)

docker-down: ## Stop all Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	$(COMPOSE_CMD) --profile full down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docker-ps: ## Show Docker service status
	@echo "$(BLUE)Docker service status:$(NC)"
	@$(COMPOSE_CMD) --profile full ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

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

.PHONY: local-up local-down local-logs local-ps local-build run-bot bot
LOCAL_SERVICES := redis qdrant bge-m3 docling litellm

local-up:  ## Start local Docker services (bot runs via make run-bot)
	$(COMPOSE_CMD) up -d $(LOCAL_SERVICES)
	@echo "$(GREEN)✓ Local services started. Run bot: make run-bot$(NC)"

run-bot:  ## Run bot locally (requires: make local-up)
	uv run --env-file .env python -m telegram_bot.main

bot:  ## Alias: run bot and tee output to logs/bot-run.log
	@mkdir -p logs
	uv run --env-file .env python -m telegram_bot.main 2>&1 | tee logs/bot-run.log; echo '[COMPLETE]'

local-down:  ## Stop local Docker services
	$(COMPOSE_CMD) stop $(LOCAL_SERVICES) || true
	$(COMPOSE_CMD) rm -f $(LOCAL_SERVICES) || true

local-logs:  ## View local Docker logs
	$(COMPOSE_CMD) logs -f $(LOCAL_SERVICES)

local-ps:  ## Show local Docker status
	$(COMPOSE_CMD) ps $(LOCAL_SERVICES)

local-build:  ## Rebuild local Docker services
	$(COMPOSE_CMD) build bge-m3 docling

# =============================================================================
# Deployment
# =============================================================================

.PHONY: deploy-code deploy-release deploy-bot

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

deploy-bot:  ## Deploy all services to VPS (git push + SSH rebuild)
	@echo "$(CYAN)Pushing to origin...$(NC)"
	git push origin main
	@echo "$(CYAN)Deploying on VPS...$(NC)"
	ssh vps "cd /opt/rag-fresh && git pull origin main && \
		docker compose build && \
		docker compose --compatibility up -d"
	@echo "$(GREEN)Deployed. Waiting for startup...$(NC)"
	@sleep 20
	ssh vps "docker ps --format '{{.Names}} {{.Status}}' | grep -E 'vps-.*(Up|healthy)'"
	@echo "$(GREEN)✓ Deploy complete$(NC)"

# =============================================================================
# E2E TESTING
# =============================================================================

.PHONY: e2e-install e2e-generate-data e2e-index-data e2e-test e2e-test-traces e2e-test-group e2e-telegram-test e2e-setup

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
	uv run python scripts/e2e/runner.py
	@echo "$(GREEN)✓ Telegram E2E runner complete$(NC)"

e2e-test-traces: ## Run E2E tests + validate Langfuse traces
	@echo "$(BLUE)Running E2E tests with Langfuse trace validation...$(NC)"
	E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py
	@echo "$(GREEN)✓ E2E tests with trace validation complete$(NC)"

e2e-test-group: ## Run specific test group (usage: make e2e-test-group GROUP=filters)
	uv run python scripts/e2e/runner.py --group $(GROUP)

e2e-setup: e2e-install ## Full E2E setup on canonical collection
	@echo "$(YELLOW)Using canonical collection via E2E_COLLECTION_NAME (default: gdrive_documents_bge)$(NC)"
	@echo "$(GREEN)✓ E2E setup complete$(NC)"

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
	$(COMPOSE_CMD) --profile obs up -d
	@echo "$(GREEN)✓ Monitoring stack started$(NC)"
	@echo "$(YELLOW)Services:$(NC)"
	@echo "  Loki:         http://localhost:3100"
	@echo "  Alertmanager: http://localhost:9093"

monitoring-down: ## Stop monitoring stack
	@echo "$(BLUE)Stopping monitoring stack...$(NC)"
	$(COMPOSE_CMD) --profile obs stop
	@echo "$(GREEN)✓ Monitoring stack stopped$(NC)"

monitoring-logs: ## View monitoring stack logs
	@echo "$(BLUE)Monitoring stack logs (Ctrl+C to exit):$(NC)"
	$(COMPOSE_CMD) logs -f loki promtail alertmanager

monitoring-status: ## Show monitoring stack status
	@echo "$(BLUE)Monitoring stack status:$(NC)"
	@$(COMPOSE_CMD) ps loki promtail alertmanager
	@echo ""
	@echo "$(YELLOW)Checking health...$(NC)"
	@curl -s http://localhost:3100/ready > /dev/null 2>&1 && echo "  Loki: $(GREEN)OK$(NC)" || echo "  Loki: $(RED)DOWN$(NC)"
	@curl -s http://localhost:9093/-/healthy > /dev/null 2>&1 && echo "  Alertmanager: $(GREEN)OK$(NC)" || echo "  Alertmanager: $(RED)DOWN$(NC)"
	@docker logs dev-promtail 2>&1 | tail -1 | grep -q "level=info" && echo "  Promtail: $(GREEN)OK$(NC)" || echo "  Promtail: $(YELLOW)CHECK LOGS$(NC)"

monitoring-test-alert: ## Send a test alert to verify Telegram integration
	@echo "$(BLUE)Sending test alert...$(NC)"
	@# Load local env (repo uses .env -> .env.local symlink) so `make` works without manual `source`.
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
	sudo mkdir -p /opt/scripts /opt/credentials /data/drive-sync
	sudo cp docker/rclone/sync-drive.sh /opt/scripts/
	sudo cp docker/rclone/gdrive-manifest.sh /opt/scripts/
	sudo chmod +x /opt/scripts/sync-drive.sh /opt/scripts/gdrive-manifest.sh
	sudo cp docker/rclone/crontab /etc/cron.d/rclone-sync
	sudo chmod 644 /etc/cron.d/rclone-sync
	@echo "$(GREEN)✓ Cron installed$(NC)"

sync-drive-run: ## Run Drive sync manually
	@echo "$(BLUE)Syncing Google Drive...$(NC)"
	/opt/scripts/sync-drive.sh
	@echo "$(GREEN)✓ Sync complete$(NC)"

sync-drive-status: ## Show sync status and recent files
	@echo "$(BLUE)Recent synced files:$(NC)"
	@ls -lt /data/drive-sync 2>/dev/null | head -20 || echo "No files synced yet"
	@echo ""
	@echo "$(BLUE)Last sync log:$(NC)"
	@tail -10 /var/log/rclone-sync.log 2>/dev/null || echo "No logs yet"

# =============================================================================
# DOCUMENT INGESTION (CocoIndex Pipeline)
# =============================================================================

.PHONY: ingest-setup ingest-dir ingest-gdrive ingest-status ingest-services ingest-test

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

ingest-gdrive: ## [DEPRECATED] Use ingest-gdrive-run instead (rclone + CocoIndex pipeline)
	@echo "$(RED)⚠ make ingest-gdrive is deprecated.$(NC)"
	@echo "  GDrive ingestion now uses rclone sync + CocoIndex pipeline."
	@echo "  Use one of:"
	@echo "    make ingest-gdrive-run    # Run ingestion once"
	@echo "    make ingest-gdrive-watch  # Continuous watch mode"
	@echo "    make ingest-gdrive-status # Collection stats"
	@exit 1

ingest-status: ## Show collection statistics
	@echo "$(BLUE)Collection status:$(NC)"
	uv run python -m telegram_bot.services.ingestion_cocoindex status

ingest-services: ## Index curated services.yaml content into Qdrant
	@echo "$(BLUE)Indexing services.yaml content...$(NC)"
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; uv run python scripts/index_services.py
	@echo "$(GREEN)✓ services.yaml indexing complete$(NC)"

# =============================================================================
# GOOGLE DRIVE INGESTION (rclone + watcher pipeline)
# =============================================================================

.PHONY: ingest-gdrive-setup ingest-gdrive-run ingest-gdrive-watch ingest-gdrive-status

ingest-gdrive-setup: ## Setup GDrive collection in Qdrant (scalar + binary)
	@echo "$(BLUE)Creating Qdrant collections...$(NC)"
	uv run python scripts/setup_scalar_collection.py --source gdrive_documents
	uv run python scripts/setup_binary_collection.py --source gdrive_documents
	@echo "$(GREEN)✓ Collections ready$(NC)"

ingest-gdrive-run: ## Run GDrive ingestion once
	@echo "$(BLUE)Running GDrive ingestion...$(NC)"
	uv run python -m src.ingestion.gdrive_flow --once
	@echo "$(GREEN)✓ Ingestion complete$(NC)"

ingest-gdrive-watch: ## Run GDrive ingestion continuously (watch mode)
	@echo "$(BLUE)Starting GDrive watch mode...$(NC)"
	uv run python -m src.ingestion.gdrive_flow --watch

ingest-gdrive-status: ## Show GDrive collection stats
	@echo "$(BLUE)GDrive collection stats:$(NC)"
	@uv run python -c "from qdrant_client import QdrantClient; c=QdrantClient('http://localhost:6333'); \
		[print(f'  {n}: {c.get_collection(n).points_count} points') if c.collection_exists(n) else print(f'  {n}: not found') \
		for n in ['gdrive_documents_scalar', 'gdrive_documents_binary']]"

# =============================================================================
# UNIFIED INGESTION PIPELINE (v3.2.1)
# =============================================================================

.PHONY: ingest-unified ingest-unified-watch ingest-unified-status ingest-unified-reprocess ingest-unified-logs

ingest-unified: ## Run unified ingestion once
	@echo "$(BLUE)Running unified ingestion (CocoIndex)...$(NC)"
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; uv run python -m src.ingestion.unified.cli run
	@echo "$(GREEN)✓ Ingestion complete$(NC)"

ingest-unified-watch: ## Run unified ingestion continuously (watch mode)
	@echo "$(BLUE)Starting unified ingestion watch mode...$(NC)"
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; uv run python -m src.ingestion.unified.cli run --watch

ingest-unified-status: ## Show unified ingestion status
	@echo "$(BLUE)Unified ingestion status:$(NC)"
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; uv run python -m src.ingestion.unified.cli status

ingest-unified-reprocess: ## Reprocess all error files
	@echo "$(BLUE)Reprocessing error files...$(NC)"
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; uv run python -m src.ingestion.unified.cli reprocess --errors
	@echo "$(GREEN)✓ Reprocess queued$(NC)"

ingest-unified-logs: ## Show ingestion service logs
	docker logs dev-ingestion -f --tail 100

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

validate-traces: ## Full rebuild + trace validation + report
	@echo "$(BLUE)Full rebuild + validation...$(NC)"
	$(COMPOSE_CMD) build --no-cache bot litellm bge-m3
	$(COMPOSE_CMD) --profile core --profile bot --profile ml up -d --wait
	uv run python scripts/validate_traces.py --report
	@echo "$(GREEN)Validation complete — see docs/reports/$(NC)"

validate-traces-fast: ## No rebuild; trace validation fails if required trace families are missing
	@echo "$(BLUE)Fast validation (no rebuild)...$(NC)"
	$(COMPOSE_CMD) --profile core --profile bot --profile ml up -d --wait
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
	kubectl create secret generic api-keys --from-env-file=k8s/secrets/.env -n rag --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic db-credentials \
		--from-literal=POSTGRES_USER=postgres \
		--from-literal=POSTGRES_PASSWORD=postgres \
		--from-literal=POSTGRES_DB=postgres \
		-n rag --dry-run=client -o yaml | kubectl apply -f -

k3s-ingest-start: ## Scale ingestion to 1 replica
	kubectl scale deployment ingestion -n rag --replicas=1

k3s-ingest-stop: ## Scale ingestion to 0 replicas
	kubectl scale deployment ingestion -n rag --replicas=0

k3s-push-%: ## Build and push image to VPS k3s: make k3s-push-bot
	docker save rag/$*:latest | ssh vps 'sudo k3s ctr -n k8s.io images import -'

# =============================================================================
# DOCKER IMAGE DRIFT (#322)
# =============================================================================

.PHONY: verify-compose-images verify-compose-images-json

verify-compose-images: ## Check running containers match compose-pinned images
	@uv run python scripts/check_image_drift.py --fix

verify-compose-images-json: ## Check image drift (JSON output for CI)
	@uv run python scripts/check_image_drift.py --json

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
