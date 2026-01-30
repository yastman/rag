# UV Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from pip/requirements.txt to uv + PEP 735 dependency groups for reproducible builds.

**Architecture:** Single source of truth in pyproject.toml with uv.lock. Mode: no-install-project (deps only, run via `uv run`). ML-service bge-m3-api gets separate pyproject.toml + uv.lock. All Dockerfiles and Makefile switch to uv.

**Tech Stack:** uv 0.9.x (pinned), Python 3.11+, PEP 735 dependency-groups, Docker with uv

**Design Document:** `docs/plans/2026-01-30-uv-migration-design.md`

---

## Prerequisites

Before starting, ensure:
1. uv is installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Docker is running: `docker ps`
3. Current tests pass: `pytest tests/unit -v` (should pass)

---

## Task 1: Create pyproject.toml for bge-m3-api

**Files:**
- Create: `services/bge-m3-api/pyproject.toml`

**Step 1: Create pyproject.toml**

Create file `services/bge-m3-api/pyproject.toml`:

```toml
[project]
name = "bge-m3-api"
version = "1.0.0"
description = "BGE-M3 Embeddings API - FastAPI service"
requires-python = ">=3.11"
dependencies = [
    # Core ML/Embeddings
    "FlagEmbedding==1.3.5",
    "torch==2.10.0",
    "transformers==4.57.6",
    "sentence-transformers==3.4.1",
    # FastAPI & Web Server
    "fastapi==0.128.0",
    "uvicorn[standard]==0.40.0",
    "python-multipart==0.0.22",
    "pydantic==2.12.5",
    "pydantic-settings==2.12.0",
    # Monitoring & Metrics
    "prometheus-client==0.24.1",
    # Utilities
    "numpy==1.26.4",
    "scipy==1.17.0",
]

[tool.uv]
# Use CPU-only PyTorch wheels to avoid CUDA dependencies and reduce image size
index-url = "https://download.pytorch.org/whl/cpu"
```

**Step 2: Verify file created**

Run: `cat services/bge-m3-api/pyproject.toml | head -10`
Expected: Shows project name and version

**Step 3: Commit**

```bash
git add services/bge-m3-api/pyproject.toml
git commit -m "feat(bge-m3): add pyproject.toml for uv migration"
```

---

## Task 2: Generate uv.lock for bge-m3-api

**Files:**
- Create: `services/bge-m3-api/uv.lock`

**Step 1: Generate lock file**

Run:
```bash
cd services/bge-m3-api && uv lock && cd ../..
```

Expected: Creates `services/bge-m3-api/uv.lock` file

**Step 2: Verify lock file**

Run: `head -20 services/bge-m3-api/uv.lock`
Expected: Shows version = 1 and package entries

**Step 3: Test lock resolves correctly**

Run:
```bash
cd services/bge-m3-api && uv lock --check && cd ../..
```

Expected: No output (success)

**Step 4: Commit**

```bash
git add services/bge-m3-api/uv.lock
git commit -m "chore(bge-m3): generate uv.lock"
```

---

## Task 3: Update bge-m3-api Dockerfile

**Files:**
- Modify: `services/bge-m3-api/Dockerfile`

**Step 1: Read current Dockerfile**

Run: `cat services/bge-m3-api/Dockerfile`

**Step 2: Replace Dockerfile content**

Replace entire `services/bge-m3-api/Dockerfile` with:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Install build dependencies (in case any package needs compilation)
# Can be removed if all deps have pre-built wheels for linux/amd64
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned version for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

# Cache: copy only dependency files first
COPY pyproject.toml uv.lock ./

# Install dependencies (frozen = use lock as-is, no-install-project = deps only)
RUN uv sync --frozen --no-install-project

# Copy application code
COPY app.py config.py ./

# Environment
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"

# Run with uv
CMD ["uv", "run", "python", "app.py"]
```

**Note:** If all packages have pre-built wheels for python:3.11-slim, the build-essential step can be removed to reduce image size.

**Step 3: Verify Dockerfile syntax**

Run: `docker build --check services/bge-m3-api/ 2>&1 | head -5`
Expected: No syntax errors (or "unknown flag: --check" which is fine)

**Step 4: Commit**

```bash
git add services/bge-m3-api/Dockerfile
git commit -m "feat(bge-m3): migrate Dockerfile to uv"
```

---

## Task 4: Test bge-m3-api Docker build

**Files:**
- None (verification only)

**Step 1: Build Docker image**

Run:
```bash
docker build -t bge-m3-test services/bge-m3-api/
```

Expected: Build completes successfully (may take several minutes due to torch)

**Step 2: Verify image created**

Run: `docker images bge-m3-test`
Expected: Shows image with size ~5-8GB

**Step 3: Remove test image**

Run: `docker rmi bge-m3-test`

**Step 4: No commit needed (verification task)**

---

## Task 5: Add dependency-groups to root pyproject.toml

**Files:**
- Modify: `pyproject.toml:1-60`

**Step 1: Update requires-python**

In `pyproject.toml`, change line 5:
```toml
# FROM:
requires-python = ">=3.9"
# TO:
requires-python = ">=3.11"
```

**Step 2: Add dependency-groups section after optional-dependencies**

After line 60 (after the `all = [...]` section), add the following.

**IMPORTANT:** Do NOT add any `---` separators — this is TOML, not YAML. Just add a blank line and the new section:

```toml
[dependency-groups]
# For uv sync --group dev
dev = [
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pylint>=3.2.0",
    "bandit>=1.7.9",
    "vulture>=2.11",
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-httpx>=0.35.0",
    "pre-commit>=3.8.0",
]
docs = [
    "mkdocs>=1.6.0",
    "mkdocs-material>=9.5.0",
    "mkdocstrings[python]>=0.25.0",
]
bot = [
    "aiogram>=3.15.0",
    "httpx>=0.28.0",
    "redis>=5.0.0",
    "redisvl>=0.3.0",
    "cachetools>=5.3.0",
]
e2e = [
    "telethon>=1.36.0",
    "anthropic>=0.39.0",
    "jinja2>=3.1.0",
    "rich>=13.0.0",
]
```

**Step 3: Update tool.ruff target-version**

In `pyproject.toml`, change line 106:
```toml
# FROM:
target-version = "py39"
# TO:
target-version = "py311"
```

**Step 4: Update tool.mypy python_version**

In `pyproject.toml`, change line 205:
```toml
# FROM:
python_version = "3.9"
# TO:
python_version = "3.11"
```

**Step 5: Update tool.pylint py-version**

In `pyproject.toml`, change line 237:
```toml
# FROM:
py-version = "3.9"
# TO:
py-version = "3.11"
```

**Step 6: Verify changes**

Run: `grep -E "requires-python|target-version|python_version|py-version" pyproject.toml`
Expected: All show 3.11

**Step 7: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add PEP 735 dependency-groups, bump to Python 3.11+"
```

---

## Task 6: Generate uv.lock for root project

**Files:**
- Create: `uv.lock`

**Step 1: Generate lock file**

Run: `uv lock`
Expected: Creates `uv.lock` in project root

**Step 2: Verify lock file**

Run: `head -30 uv.lock`
Expected: Shows version = 1 and resolution-markers

**Step 3: Verify lock is consistent**

Run: `uv lock --check`
Expected: No output (success)

**Step 4: Commit**

```bash
git add uv.lock
git commit -m "chore: generate uv.lock"
```

---

## Task 7: Test uv sync works

**Files:**
- None (verification only)

**Step 1: Remove existing venv**

Run: `rm -rf .venv`

**Step 2: Sync with dev + bot groups**

Run: `uv sync --group dev --group bot --no-install-project`
Expected: Creates .venv and installs all dependencies

**Step 3: Verify Python version**

Run: `uv run python --version`
Expected: Python 3.11.x or 3.12.x

**Step 4: Verify pytest works**

Run: `uv run pytest tests/unit -v --co -q | head -20`
Expected: Shows collected tests

**Step 5: Run unit tests**

Run: `uv run pytest tests/unit -v`
Expected: All tests pass

**Step 6: No commit needed (verification task)**

---

## Task 8: Update Makefile for uv

**Files:**
- Modify: `Makefile:22-36` and add new section

**Step 1: Replace install targets**

Replace lines 22-36 in `Makefile` with:

```makefile
# =============================================================================
# DEPENDENCY MANAGEMENT (uv)
# =============================================================================

install: ## Install runtime dependencies
	uv sync --no-install-project

install-dev: ## Install development dependencies (runtime + dev + bot)
	uv sync --group dev --group bot --no-install-project

install-all: ## Install all dependencies (all groups)
	uv sync --all-groups --no-install-project

lock: pyproject.toml ## Update lock after changing pyproject.toml
	uv lock

sync: ## Sync dependencies (local development)
	uv sync --no-install-project

sync-frozen: ## Strict sync (CI/VPS/Docker)
	uv sync --frozen --no-install-project

upgrade: ## Upgrade all packages to latest versions
	uv lock --upgrade

upgrade-package: ## Upgrade specific package (usage: make upgrade-package PKG=httpx)
	uv lock --upgrade-package $(PKG)

clean-venv: ## Recreate virtual environment from scratch
	rm -rf .venv
	uv sync --group dev --group bot --no-install-project

export-requirements-legacy: ## Export for legacy infrastructure (not for installation!)
	uv export --format requirements.txt --no-hashes -o requirements.txt

print-deps: ## Show dependency tree
	uv tree

doctor: ## Check environment health
	@echo "=== uv version ==="
	@uv --version
	@echo "=== Python version ==="
	@uv run python --version
	@echo "=== Lock status ==="
	@uv lock --check && echo "Lock is up-to-date" || echo "Lock is outdated, run: make lock"
```

**Step 2: Update lint target to use uv run**

Find line with `ruff check src/` and replace the entire lint section (lines ~41-49):

```makefile
lint: ## Run Ruff linter (fast)
	@echo "$(BLUE)Running Ruff linter...$(NC)"
	uv run ruff check src/ telegram_bot/
	@echo "$(GREEN)✓ Ruff check complete$(NC)"

lint-fix: ## Run Ruff linter with auto-fix
	@echo "$(BLUE)Running Ruff with auto-fix...$(NC)"
	uv run ruff check src/ telegram_bot/ --fix
	@echo "$(GREEN)✓ Ruff auto-fix complete$(NC)"
```

**Step 3: Update format target**

Replace format section (~lines 51-59):

```makefile
format: ## Format code with Ruff
	@echo "$(BLUE)Formatting code with Ruff...$(NC)"
	uv run ruff format src/ telegram_bot/
	@echo "$(GREEN)✓ Code formatted$(NC)"

format-check: ## Check if code is formatted
	@echo "$(BLUE)Checking code format...$(NC)"
	uv run ruff format src/ telegram_bot/ --check
	@echo "$(GREEN)✓ Format check complete$(NC)"
```

**Step 4: Update type-check target**

Replace type-check line (~line 62):

```makefile
type-check: ## Run MyPy type checking
	@echo "$(BLUE)Running MyPy type checking...$(NC)"
	uv run mypy src/ telegram_bot/ --ignore-missing-imports
	@echo "$(GREEN)✓ Type check complete$(NC)"
```

**Step 5: Update test targets**

Replace test section (~lines 88-112):

```makefile
test: ## Run tests with pytest
	@echo "$(BLUE)Running tests...$(NC)"
	uv run pytest tests/
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest tests/ --cov=src --cov=telegram_bot --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests with coverage complete$(NC)"
	@echo "$(YELLOW)Open htmlcov/index.html to view coverage report$(NC)"

test-unit: ## Run only unit tests (fast, no external deps)
	@echo "$(BLUE)Running unit tests...$(NC)"
	uv run pytest tests/unit/ -v
	@echo "$(GREEN)✓ Unit tests complete$(NC)"
```

**Step 6: Update e2e-install**

Replace e2e-install (~line 294):

```makefile
e2e-install: ## Install E2E testing dependencies
	@echo "$(BLUE)Installing E2E dependencies...$(NC)"
	uv sync --group e2e --no-install-project
	@echo "$(GREEN)✓ E2E dependencies installed$(NC)"
```

**Step 7: Verify Makefile syntax**

Run: `make help`
Expected: Shows help without errors

**Step 8: Test make install-dev**

Run: `make install-dev`
Expected: Runs uv sync successfully

**Step 9: Test make test-unit**

Run: `make test-unit`
Expected: Unit tests pass

**Step 10: Commit**

```bash
git add Makefile
git commit -m "feat: migrate Makefile to uv commands"
```

---

## Task 9: Update bot Dockerfile

**Files:**
- Modify: `telegram_bot/Dockerfile`

**Step 1: Replace Dockerfile content**

Replace entire `telegram_bot/Dockerfile` with:

```dockerfile
# syntax=docker/dockerfile:1
# Telegram Bot Dockerfile - uv-based build

FROM python:3.12-slim

WORKDIR /app

# Install build dependencies (in case any package needs compilation)
# Can be removed if all deps have pre-built wheels for linux/amd64
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (pinned version for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

# Cache: copy only dependency files first
COPY pyproject.toml uv.lock ./

# Install dependencies (frozen = use lock as-is, no-install-project = deps only)
# Include bot group for telegram-specific deps
RUN uv sync --frozen --group bot --no-install-project

# Copy application code
COPY telegram_bot/ ./telegram_bot/
COPY src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD uv run python -c "from telegram_bot.bot import PropertyBot" || exit 1

# Run bot with uv
CMD ["uv", "run", "python", "-m", "telegram_bot.main"]
```

**Note:** If all packages have pre-built wheels, the build-essential step can be removed. Current bot deps (aiogram, httpx, redis) typically have wheels available.

**Step 2: Commit**

```bash
git add telegram_bot/Dockerfile
git commit -m "feat(bot): migrate Dockerfile to uv"
```

---

## Task 10: Test bot Docker build

**Files:**
- None (verification only)

**Step 1: Build bot image**

Run:
```bash
docker build -t bot-test -f telegram_bot/Dockerfile .
```

Expected: Build completes successfully

**Step 2: Verify image**

Run: `docker images bot-test`
Expected: Shows image

**Step 3: Remove test image**

Run: `docker rmi bot-test`

**Step 4: No commit needed (verification task)**

---

## Task 11: Update CI workflow

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Replace CI workflow**

Replace entire `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: [main, development]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.9.26"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --frozen --group dev --no-install-project

      - name: Ruff lint
        run: uv run ruff check src/ telegram_bot/ tests/ --output-format=github

      - name: Ruff format check
        run: uv run ruff format --check src/ telegram_bot/ tests/

      - name: Type check
        run: uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary || true

  test:
    name: Unit Tests
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.9.26"

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --frozen --group dev --group bot --no-install-project

      - name: Run unit tests
        run: uv run pytest tests/unit -v

  lock-check:
    name: Lock File Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "0.9.26"

      - name: Check lock is up-to-date
        run: uv lock --check
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat(ci): migrate to uv"
```

---

## Task 12: Mark legacy requirements files

**Files:**
- Modify: `requirements.txt` (add header comment)
- Modify: `telegram_bot/requirements.txt` (add header comment)
- Modify: `requirements-e2e.txt` (add header comment)

**Step 1: Add legacy header to requirements.txt**

Prepend to `requirements.txt`:

```
# =============================================================================
# LEGACY FILE - DO NOT EDIT
# =============================================================================
# This file is kept for reference only.
# Source of truth: pyproject.toml + uv.lock
# To regenerate: make export-requirements-legacy
# =============================================================================

```

**Step 2: Add legacy header to telegram_bot/requirements.txt**

Prepend to `telegram_bot/requirements.txt`:

```
# =============================================================================
# LEGACY FILE - DO NOT EDIT
# =============================================================================
# Dependencies are now in pyproject.toml [dependency-groups].bot
# This file is kept for reference only.
# =============================================================================

```

**Step 3: Add legacy header to requirements-e2e.txt**

Prepend to `requirements-e2e.txt`:

```
# =============================================================================
# LEGACY FILE - DO NOT EDIT
# =============================================================================
# Dependencies are now in pyproject.toml [dependency-groups].e2e
# This file is kept for reference only.
# =============================================================================

```

**Step 4: Commit**

```bash
git add requirements.txt telegram_bot/requirements.txt requirements-e2e.txt
git commit -m "docs: mark requirements files as legacy"
```

---

## Task 13: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (add new section after "Build & Development Commands")

**Step 1: Find "Build & Development Commands" section**

Search for line with `## Build & Development Commands`

**Step 2: Add uv section after that section**

After the existing commands table, add:

```markdown

## Dependency Management (uv + PEP 735)

**Mode:** no-install-project (deps only, run via `uv run`)

**Rules:**
1. Зависимости только в `pyproject.toml` — никогда не редактировать requirements*.txt
2. `uv.lock` обязателен в PR — `uv lock --check` проверяется в CI
3. Docker/CI используют `--frozen` — гарантия воспроизводимости
4. Никогда `pip install <package>` — только через pyproject.toml + uv lock

**Команды:**
```bash
make install-dev          # runtime + dev + bot
make lock                 # обновить lock после изменения pyproject.toml
make upgrade-package PKG=httpx  # обновить конкретный пакет
make doctor               # проверка окружения
make sync-frozen          # CI/Docker режим
```

**Структура зависимостей:**
- Root: `/pyproject.toml` + `/uv.lock`
- ML-сервисы: `services/*/pyproject.toml` + `services/*/uv.lock` (независимые)

**Dependency Groups (PEP 735):**
| Group | Назначение |
|-------|------------|
| dev | ruff, mypy, pytest, pre-commit |
| docs | mkdocs |
| bot | aiogram, httpx, redis |
| e2e | telethon, anthropic |

```

**Step 3: Update Quick Reference section**

Find `## Quick Reference` and update commands:

```markdown
## Quick Reference

```bash
make check              # Lint + types
make test               # All tests
make test-unit          # Unit tests only (fast, no deps)
make install-dev        # Install dev deps with uv
make lock               # Update uv.lock after pyproject.toml change
make doctor             # Check environment health
make docker-up          # Start Qdrant, Redis, MLflow
. .venv/bin/activate    # Activate venv (created by uv)
```
```

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add uv dependency management to CLAUDE.md"
```

---

## Task 14: Final verification

**Files:**
- None (verification only)

**Step 1: Clean slate test**

Run:
```bash
rm -rf .venv
make install-dev
```

Expected: Creates fresh .venv with all deps

**Step 2: Run full test suite**

Run: `make test-unit`
Expected: All unit tests pass

**Step 3: Verify doctor**

Run: `make doctor`
Expected: Shows uv version, Python 3.11+, lock up-to-date

**Step 4: Verify CI would pass**

Run:
```bash
uv run ruff check src/ telegram_bot/ tests/
uv run ruff format --check src/ telegram_bot/ tests/
uv lock --check
```

Expected: All pass

**Step 5: Build Docker images**

Run:
```bash
docker compose -f docker-compose.dev.yml build bot bge-m3
```

Expected: Both build successfully

**Step 6: No commit needed (final verification)**

---

## Task 15: Create summary commit

**Step 1: Review all changes**

Run: `git log --oneline -10`
Expected: Shows all migration commits

**Step 2: Verify working tree clean**

Run: `git status`
Expected: Nothing to commit, working tree clean

**Step 3: Tag migration complete**

```bash
git tag -a uv-migration-complete -m "Completed migration to uv + PEP 735"
```

---

## Rollback Plan

If issues arise after migration:

1. **Revert Dockerfile changes:**
   ```bash
   git checkout HEAD~5 -- telegram_bot/Dockerfile services/bge-m3-api/Dockerfile
   ```

2. **Use legacy requirements:**
   ```bash
   rm -rf .venv
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Full rollback:**
   ```bash
   git revert --no-commit HEAD~N..HEAD  # N = number of commits
   git commit -m "revert: rollback uv migration"
   ```
