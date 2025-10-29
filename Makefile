.PHONY: help install install-dev lint format type-check security test test-cov clean all-checks

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
	pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ***REMOVED******REMOVED*** Run only unit tests
	@echo "$(BLUE)Running unit tests...$(NC)"
	pytest tests/unit/
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-integration: ***REMOVED******REMOVED*** Run only integration tests
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/integration/
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

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
