.PHONY: help install install-dev lint format type-check security test test-cov clean all-checks \
	test-preflight test-smoke test-smoke-routing test-load test-load-ci test-load-eviction \
	test-load-update-baseline test-all-smoke-load smoke-fast smoke-zoo

***REMOVED*** Default target
.DEFAULT_GOAL := help

***REMOVED*** Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m ***REMOVED*** No Color

help: ***REMOVED******REMOVED*** Show this help message
	@echo "$(BLUE)Contextual RAG v2.0.1 - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?***REMOVED******REMOVED*** .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?***REMOVED******REMOVED*** "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

install: ***REMOVED******REMOVED*** Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	pip install -e .
	@echo "$(GREEN)✓ Production dependencies installed$(NC)"

install-dev: ***REMOVED******REMOVED*** Install development dependencies (linters, formatters, etc.)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	pip install -e ".[dev]"
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

install-all: ***REMOVED******REMOVED*** Install all dependencies (prod + dev + docs)
	@echo "$(BLUE)Installing all dependencies...$(NC)"
	pip install -e ".[all]"
	@echo "$(GREEN)✓ All dependencies installed$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** CODE QUALITY CHECKS
***REMOVED*** =============================================================================

lint: ***REMOVED******REMOVED*** Run Ruff linter (fast)
	@echo "$(BLUE)Running Ruff linter...$(NC)"
	ruff check src/
	@echo "$(GREEN)✓ Ruff check complete$(NC)"

lint-fix: ***REMOVED******REMOVED*** Run Ruff linter with auto-fix
	@echo "$(BLUE)Running Ruff with auto-fix...$(NC)"
	ruff check src/ --fix
	@echo "$(GREEN)✓ Ruff auto-fix complete$(NC)"

format: ***REMOVED******REMOVED*** Format code with Ruff
	@echo "$(BLUE)Formatting code with Ruff...$(NC)"
	ruff format src/
	@echo "$(GREEN)✓ Code formatted$(NC)"

format-check: ***REMOVED******REMOVED*** Check if code is formatted
	@echo "$(BLUE)Checking code format...$(NC)"
	ruff format src/ --check
	@echo "$(GREEN)✓ Format check complete$(NC)"

type-check: ***REMOVED******REMOVED*** Run MyPy type checking
	@echo "$(BLUE)Running MyPy type checking...$(NC)"
	mypy src/ --ignore-missing-imports
	@echo "$(GREEN)✓ Type check complete$(NC)"

pylint: ***REMOVED******REMOVED*** Run Pylint (comprehensive linting)
	@echo "$(BLUE)Running Pylint...$(NC)"
	pylint src/ --rcfile=pyproject.toml || true
	@echo "$(GREEN)✓ Pylint check complete$(NC)"

security: ***REMOVED******REMOVED*** Run Bandit security checks
	@echo "$(BLUE)Running Bandit security checks...$(NC)"
	bandit -r src/ -c pyproject.toml
	@echo "$(GREEN)✓ Security check complete$(NC)"

dead-code: ***REMOVED******REMOVED*** Find dead code with Vulture
	@echo "$(BLUE)Checking for dead code...$(NC)"
	vulture src/ --min-confidence 80
	@echo "$(GREEN)✓ Dead code check complete$(NC)"

all-checks: lint type-check security ***REMOVED******REMOVED*** Run all code quality checks
	@echo "$(GREEN)✓✓✓ All checks passed! ✓✓✓$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** TESTING
***REMOVED*** =============================================================================

test: ***REMOVED******REMOVED*** Run tests with pytest
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-cov: ***REMOVED******REMOVED*** Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest tests/ --cov=src --cov=telegram_bot --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ***REMOVED******REMOVED*** Run only unit tests (fast, no external deps)
	@echo "$(BLUE)Running unit tests...$(NC)"
	pytest tests/unit/ -v
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-integration: ***REMOVED******REMOVED*** Run only integration tests (requires Docker/API keys)
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/integration/ -v
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

test-all: ***REMOVED******REMOVED*** Run all tests with coverage threshold (CI mode)
	@echo "$(BLUE)Running all tests with coverage...$(NC)"
	pytest tests/ -v --cov=src --cov=telegram_bot --cov-report=term-missing --cov-fail-under=80
	@echo "$(GREEN)✓ All tests passed with 80%+ coverage$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** SMOKE & LOAD TESTS
***REMOVED*** =============================================================================

test-preflight: ***REMOVED******REMOVED*** Run preflight checks (Qdrant/Redis config)
	@echo "$(BLUE)Running preflight checks...$(NC)"
	pytest tests/smoke/test_preflight.py -v -s
	@echo "$(GREEN)✓ Preflight complete$(NC)"

test-smoke: ***REMOVED******REMOVED*** Run smoke tests (requires live services)
	@echo "$(BLUE)Running smoke tests...$(NC)"
	pytest tests/smoke/ -v --tb=short
	@echo "$(GREEN)✓ Smoke tests complete$(NC)"

test-smoke-routing: ***REMOVED******REMOVED*** Run smoke routing tests only (no deps)
	@echo "$(BLUE)Running smoke routing tests...$(NC)"
	pytest tests/smoke/test_smoke_routing.py -v
	@echo "$(GREEN)✓ Routing tests complete$(NC)"

test-load: ***REMOVED******REMOVED*** Run load tests (live services)
	@echo "$(BLUE)Running load tests...$(NC)"
	pytest tests/load/test_load_conversations.py -v -s
	@echo "$(GREEN)✓ Load tests complete$(NC)"

test-load-ci: ***REMOVED******REMOVED*** Run load tests in CI (mocked, fast)
	@echo "$(BLUE)Running load tests (CI mode)...$(NC)"
	LOAD_USE_MOCKS=1 LOAD_CHAT_COUNT=5 pytest tests/load/test_load_conversations.py -v
	@echo "$(GREEN)✓ Load tests (CI) complete$(NC)"

test-load-eviction: ***REMOVED******REMOVED*** Run Redis eviction tests
	@echo "$(BLUE)Running Redis eviction tests...$(NC)"
	pytest tests/load/test_load_redis_eviction.py -v -s
	@echo "$(GREEN)✓ Redis eviction tests complete$(NC)"

test-load-update-baseline: ***REMOVED******REMOVED*** Update load test baseline
	@echo "$(BLUE)Updating baseline...$(NC)"
	pytest tests/load/test_load_conversations.py -v --update-baseline
	@echo "$(GREEN)✓ Baseline updated$(NC)"

test-all-smoke-load: test-preflight test-smoke test-load ***REMOVED******REMOVED*** Full smoke+load suite
	@echo "$(GREEN)✓✓✓ All smoke+load tests complete$(NC)"

smoke-fast: ***REMOVED******REMOVED*** Quick zoo smoke (~30 sec, bash only)
	@echo "$(BLUE)Running quick zoo smoke...$(NC)"
	./scripts/smoke-zoo.sh
	@echo "$(GREEN)✓ Zoo smoke complete$(NC)"

smoke-zoo: ***REMOVED******REMOVED*** Run zoo smoke tests (pytest)
	@echo "$(BLUE)Running zoo smoke tests...$(NC)"
	pytest tests/smoke/test_zoo_smoke.py -v
	@echo "$(GREEN)✓ Zoo smoke tests complete$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** REDIS VERIFICATION
***REMOVED*** =============================================================================

.PHONY: test-redis

test-redis: ***REMOVED******REMOVED*** Verify Redis Query Engine is available
	@echo "$(BLUE)Testing Redis Query Engine...$(NC)"
	@docker exec dev-redis redis-cli FT._LIST > /dev/null 2>&1 || \
		(echo "$(RED)FAIL: FT._LIST not available - Query Engine missing$(NC)" && exit 1)
	@docker exec dev-redis redis-cli FT.CREATE __test_idx ON HASH PREFIX 1 __test: SCHEMA name TEXT > /dev/null 2>&1 || \
		(echo "$(RED)FAIL: Cannot create test index$(NC)" && exit 1)
	@docker exec dev-redis redis-cli FT.DROPINDEX __test_idx > /dev/null 2>&1 || true
	@echo "$(GREEN)✓ Redis Query Engine OK$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** PROJECT MANAGEMENT
***REMOVED*** =============================================================================

clean: ***REMOVED******REMOVED*** Clean up cache files and build artifacts
	@echo "$(BLUE)Cleaning up...$(NC)"
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned up$(NC)"

docker-up: ***REMOVED******REMOVED*** Start Qdrant and ML services
	@echo "$(BLUE)Starting Docker services...$(NC)"
	docker compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"

docker-down: ***REMOVED******REMOVED*** Stop Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** DEVELOPMENT WORKFLOW
***REMOVED*** =============================================================================

dev-setup: install-dev docker-up ***REMOVED******REMOVED*** Complete development setup
	@echo "$(GREEN)✓✓✓ Development environment ready! ✓✓✓$(NC)"
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Copy .env.example to .env"
	@echo "  2. Fill in your API keys"
	@echo "  3. Run 'make test' to verify setup"

pre-commit: lint-fix format type-check test ***REMOVED******REMOVED*** Run all checks before commit
	@echo "$(GREEN)✓✓✓ Ready to commit! ✓✓✓$(NC)"

ci: format-check lint type-check security test ***REMOVED******REMOVED*** CI/CD pipeline checks
	@echo "$(GREEN)✓✓✓ CI checks passed! ✓✓✓$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** DOCUMENTATION
***REMOVED*** =============================================================================

docs-serve: ***REMOVED******REMOVED*** Serve documentation locally
	@echo "$(BLUE)Starting documentation server...$(NC)"
	mkdocs serve
	@echo "$(GREEN)✓ Documentation server running at http://localhost:8000$(NC)"

docs-build: ***REMOVED******REMOVED*** Build documentation
	@echo "$(BLUE)Building documentation...$(NC)"
	mkdocs build
	@echo "$(GREEN)✓ Documentation built in site/$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** QUICK COMMANDS
***REMOVED*** =============================================================================

check: lint type-check ***REMOVED******REMOVED*** Quick check (lint + types)
	@echo "$(GREEN)✓ Quick check complete$(NC)"

fix: lint-fix format ***REMOVED******REMOVED*** Fix all auto-fixable issues
	@echo "$(GREEN)✓ Auto-fixes applied$(NC)"

qa: all-checks test ***REMOVED******REMOVED*** Full quality assurance
	@echo "$(GREEN)✓✓✓ Full QA complete! ✓✓✓$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** Local Development (docker-compose.local.yml)
***REMOVED*** =============================================================================

.PHONY: local-up local-down local-logs local-ps local-build

local-up:  ***REMOVED******REMOVED*** Start local Docker services
	docker compose -f docker-compose.local.yml up -d

local-down:  ***REMOVED******REMOVED*** Stop local Docker services
	docker compose -f docker-compose.local.yml down

local-logs:  ***REMOVED******REMOVED*** View local Docker logs
	docker compose -f docker-compose.local.yml logs -f

local-ps:  ***REMOVED******REMOVED*** Show local Docker status
	docker compose -f docker-compose.local.yml ps

local-build:  ***REMOVED******REMOVED*** Rebuild local Docker services
	docker compose -f docker-compose.local.yml build

***REMOVED*** =============================================================================
***REMOVED*** Deployment
***REMOVED*** =============================================================================

.PHONY: deploy-code deploy-release

deploy-code:  ***REMOVED******REMOVED*** Quick deploy (git pull only)
	git tag -d deploy-code 2>/dev/null || true
	git tag deploy-code
	git push origin deploy-code --force

deploy-release:  ***REMOVED******REMOVED*** Release deploy (requires VERSION, e.g., make deploy-release VERSION=2.6.0)
ifndef VERSION
	$(error VERSION is required. Usage: make deploy-release VERSION=2.6.0)
endif
	git tag v$(VERSION)
	git push origin v$(VERSION)

***REMOVED*** =============================================================================
***REMOVED*** E2E TESTING
***REMOVED*** =============================================================================

.PHONY: e2e-install e2e-generate-data e2e-index-data e2e-test e2e-test-traces e2e-test-group e2e-setup

e2e-install: ***REMOVED******REMOVED*** Install E2E testing dependencies
	@echo "$(BLUE)Installing E2E dependencies...$(NC)"
	pip install -r requirements-e2e.txt
	@echo "$(GREEN)✓ E2E dependencies installed$(NC)"

e2e-generate-data: ***REMOVED******REMOVED*** Generate test property data
	@echo "$(BLUE)Generating test properties...$(NC)"
	python scripts/generate_test_properties.py
	@echo "$(GREEN)✓ Test data generated$(NC)"

e2e-index-data: ***REMOVED******REMOVED*** Index test data into Qdrant
	@echo "$(BLUE)Indexing test properties...$(NC)"
	python scripts/index_test_properties.py
	@echo "$(GREEN)✓ Test data indexed$(NC)"

e2e-test: ***REMOVED******REMOVED*** Run E2E tests against Telegram bot
	@echo "$(BLUE)Running E2E tests...$(NC)"
	python scripts/e2e/runner.py
	@echo "$(GREEN)✓ E2E tests complete$(NC)"

e2e-test-traces: ***REMOVED******REMOVED*** Run E2E tests + validate Langfuse traces
	@echo "$(BLUE)Running E2E tests with Langfuse trace validation...$(NC)"
	E2E_VALIDATE_LANGFUSE=1 python scripts/e2e/runner.py
	@echo "$(GREEN)✓ E2E tests with trace validation complete$(NC)"

e2e-test-group: ***REMOVED******REMOVED*** Run specific test group (usage: make e2e-test-group GROUP=filters)
	python scripts/e2e/runner.py --group $(GROUP)

e2e-setup: e2e-install e2e-generate-data e2e-index-data ***REMOVED******REMOVED*** Full E2E setup
	@echo "$(GREEN)✓ E2E setup complete$(NC)"

***REMOVED*** =============================================================================
***REMOVED*** BASELINE & OBSERVABILITY
***REMOVED*** =============================================================================

.PHONY: baseline-smoke baseline-load baseline-compare baseline-set baseline-report baseline-check

***REMOVED*** Generate unique session ID from git commit
BASELINE_SESSION := smoke-$(shell git rev-parse --short HEAD)-$(shell date +%Y%m%d%H%M%S)
LOAD_SESSION := load-$(shell git rev-parse --short HEAD)-$(shell date +%Y%m%d%H%M%S)

baseline-smoke: ***REMOVED******REMOVED*** Run smoke tests with Langfuse tracing
	@echo "$(BLUE)Running smoke tests with Langfuse tracing...$(NC)"
	@echo "$(YELLOW)Session: $(BASELINE_SESSION)$(NC)"
	LANGFUSE_SESSION_ID="$(BASELINE_SESSION)" \
	LANGFUSE_RELEASE="$(shell git rev-parse --short HEAD)" \
	pytest tests/smoke/ -v --tb=short -x
	@echo ""
	@echo "$(GREEN)Results tagged as: $(BASELINE_SESSION)$(NC)"
	@echo "$(YELLOW)View in Langfuse: http://localhost:3001$(NC)"

baseline-load: ***REMOVED******REMOVED*** Run load tests with Langfuse tracing
	@echo "$(BLUE)Running load tests with Langfuse tracing...$(NC)"
	@echo "$(YELLOW)Session: $(LOAD_SESSION)$(NC)"
	LANGFUSE_SESSION_ID="$(LOAD_SESSION)" \
	LANGFUSE_RELEASE="$(shell git rev-parse --short HEAD)" \
	pytest tests/load/ -v --tb=short
	@echo ""
	@echo "$(GREEN)Results tagged as: $(LOAD_SESSION)$(NC)"

baseline-compare: ***REMOVED******REMOVED*** Compare current run against baseline (usage: make baseline-compare BASELINE_TAG=... CURRENT_TAG=...)
ifndef BASELINE_TAG
	$(error BASELINE_TAG is required. Usage: make baseline-compare BASELINE_TAG=smoke-abc1234-20260128 CURRENT_TAG=...)
endif
ifndef CURRENT_TAG
	$(error CURRENT_TAG is required. Usage: make baseline-compare BASELINE_TAG=... CURRENT_TAG=...)
endif
	@echo "$(BLUE)Comparing $(CURRENT_TAG) against baseline $(BASELINE_TAG)...$(NC)"
	python3 -m tests.baseline.cli compare \
		--baseline="$(BASELINE_TAG)" \
		--current="$(CURRENT_TAG)" \
		--thresholds=tests/baseline/thresholds.yaml

baseline-set: ***REMOVED******REMOVED*** Set a run as the new baseline (usage: make baseline-set TAG=...)
ifndef TAG
	$(error TAG is required. Usage: make baseline-set TAG=smoke-abc1234-20260128)
endif
	@echo "$(BLUE)Setting $(TAG) as baseline...$(NC)"
	python3 -m tests.baseline.cli set-baseline --tag="$(TAG)"

baseline-report: ***REMOVED******REMOVED*** Generate HTML baseline report
	@echo "$(BLUE)Generating baseline report...$(NC)"
	python3 -m tests.baseline.cli report \
		--output=reports/baseline-$(shell date +%Y%m%d-%H%M%S).html
	@echo "$(GREEN)Report saved to reports/$(NC)"

baseline-check: baseline-smoke ***REMOVED******REMOVED*** Quick baseline check (smoke + compare with main)
	@echo "$(BLUE)Comparing with main baseline...$(NC)"
	make baseline-compare BASELINE_TAG=main-latest CURRENT_TAG=$(BASELINE_SESSION)
