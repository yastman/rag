# Contributing Guide

> Development workflow for the Contextual RAG project

**Repository:** https://github.com/yastman/rag
**Branch:** main
**Python:** 3.12

---

## 1. Development Setup (Windows + WSL2)

### Prerequisites

- **WSL2** with Ubuntu 22.04+
- **Docker Desktop** with WSL2 backend enabled
- **Python 3.12** (via pyenv or system package)
- **Git** 2.40+

### First-Time Setup

```bash
# 1. Clone the repository
git clone https://github.com/yastman/rag.git
cd rag

# 2. Create and activate virtual environment
python3.12 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"      # Dev dependencies (linters, pytest)
# Or for all deps:
pip install -e ".[all]"      # Dev + docs

# 4. Copy environment file
cp .env.example .env
# Edit .env and add your API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)

# 5. Start Docker services (Qdrant, Redis, MLflow, Langfuse)
docker compose -f docker-compose.local.yml up -d

# 6. Install pre-commit hooks
pre-commit install --install-hooks
pre-commit install --hook-type pre-push
```

### Verify Setup

```bash
# Check Python version
python --version  # Should be 3.12.x

# Verify services
curl http://localhost:6333/health  # Qdrant
curl http://localhost:5000/health  # MLflow

# Run tests
pytest tests/
```

---

## 2. Daily Workflow

### Start Services

```bash
# Start Docker services
make local-up
# Or: docker compose -f docker-compose.local.yml up -d

# Activate virtual environment
source venv/bin/activate
```

### Development Commands

```bash
# Lint code
make lint                    # Check only
make lint-fix                # Auto-fix issues

# Format code
make format                  # Format all
make format-check            # Check only (CI)

# Type checking
make type-check              # MyPy

# Run tests
make test                    # All tests
make test-cov                # With coverage report
pytest tests/test_xxx.py     # Single test file

# All checks at once
make check                   # Quick: lint + types
make qa                      # Full: lint + types + security + tests
```

### Before Commit

```bash
# Option 1: Manual checks
make pre-commit              # lint-fix + format + type-check + test

# Option 2: Pre-commit hooks (automatic)
# Hooks run automatically on git commit:
#   - Ruff linter (with auto-fix)
#   - Ruff formatter
#   - Trailing whitespace
#   - YAML/TOML/JSON validation
#   - Large file check
```

---

## 3. Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>: <description>

- <detail 1>
- <detail 2>

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Types

| Type       | Description                                        |
|------------|----------------------------------------------------|
| `feat`     | New feature                                        |
| `fix`      | Bug fix                                            |
| `docs`     | Documentation only                                 |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test`     | Adding or updating tests                           |
| `chore`    | Build process, dependencies, configs              |
| `ci`       | CI/CD configuration                                |

### Examples

```bash
# Feature
git commit -m "feat: add semantic cache with Redis Vector Search

- Implement 4-tier caching architecture
- Add COSINE similarity with 0.85 threshold

Co-Authored-By: Claude <noreply@anthropic.com>"

# Bug fix
git commit -m "fix: correct embedding dimension mismatch in Qdrant

- Update vector size from 768 to 1024 for BGE-M3

Co-Authored-By: Claude <noreply@anthropic.com>"

# Documentation
git commit -m "docs: add contributing guide for local development workflow

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 4. Deploy Instructions

### Quick Deploy (Code Only)

Use `deploy-code` tag for fast deployments (git pull on server).

```bash
# Create and push deploy tag
make deploy-code
# Or manually:
git tag -d deploy-code 2>/dev/null || true
git tag deploy-code
git push origin deploy-code --force
```

### Release Deploy (Versioned)

Use semantic versioning `v*.*.*` tags for releases.

```bash
# Create release tag
make deploy-release VERSION=2.6.0
# Or manually:
git tag v2.6.0
git push origin v2.6.0
```

### GitHub Actions

Deployments are triggered automatically via GitHub Actions:
- `deploy-code` tag: Quick code sync
- `v*.*.*` tags: Full release deployment

---

## 5. Code Quality

### Tools

| Tool    | Purpose              | Command               |
|---------|----------------------|-----------------------|
| Ruff    | Linter + Formatter   | `make lint`, `make format` |
| MyPy    | Type Checker         | `make type-check`     |
| Bandit  | Security Scanner     | `make security`       |
| Vulture | Dead Code Detection  | `make dead-code`      |
| pytest  | Testing Framework    | `make test`           |

### Configuration

All tools are configured in `pyproject.toml`:

- **Ruff**: Line length 100, Python 3.9+ target
- **MyPy**: Strict mode with `ignore_missing_imports`
- **pytest**: Coverage for `src/`, async mode enabled

### Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:

1. **Ruff Linter** - Check and auto-fix code issues
2. **Ruff Formatter** - Format code (after linting)
3. **Pre-commit-hooks** - Trailing whitespace, YAML/TOML/JSON validation
4. **Branch Protection** - Warning on direct push to main (pre-push)

---

## 6. Project Structure

```
contextual_rag/
├── src/                     # Core RAG pipeline
│   ├── ingestion/           #   PDF/CSV/DOCX parsers + Qdrant indexing
│   ├── retrieval/           #   Hybrid search (RRF/DBSF + ColBERT)
│   ├── cache/               #   Redis 4-tier cache
│   ├── evaluation/          #   MLflow + Langfuse + RAGAS
│   ├── governance/          #   Model Registry
│   ├── security/            #   PII redaction + budget guards
│   ├── core/                #   RAG pipeline orchestration
│   └── config/              #   Configuration management
│
├── telegram_bot/            # Telegram bot interface (if exists)
│
├── services/                # Docker service configs
│   └── bge-m3-api/          #   BGE-M3 embedding service
│
├── tests/                   # Test suite
│   ├── test_*.py            #   Integration tests
│   └── data/                #   Test fixtures
│
├── docs/                    # Documentation
│   ├── PIPELINE_OVERVIEW.md #   System architecture
│   └── implementation/      #   Implementation details
│
├── deploy/                  # Server configuration
│   └── telegram-bot.service #   Systemd service file
│
├── evaluation/              # Evaluation data and reports
│   ├── data/                #   Test datasets
│   └── reports/             #   Evaluation results
│
├── scripts/                 # Utility scripts
│   ├── qdrant_backup.sh     #   Backup Qdrant
│   └── qdrant_restore.sh    #   Restore Qdrant
│
├── data/                    # Data files
│   └── demo/                #   Demo documents
│
├── legacy/                  # Deprecated code
│
├── pyproject.toml           # Project config (deps, tools)
├── Makefile                 # Development commands
├── docker-compose.local.yml # Local Docker services
├── .pre-commit-config.yaml  # Pre-commit hooks config
├── .env.example             # Environment template
└── README.md                # Project overview
```

---

## 7. Useful Commands

| Task                          | Command                                |
|-------------------------------|----------------------------------------|
| **Setup**                     |                                        |
| Install dev dependencies      | `pip install -e ".[dev]"`              |
| Start Docker services         | `make local-up`                        |
| Stop Docker services          | `make local-down`                      |
| View Docker logs              | `make local-logs`                      |
| **Code Quality**              |                                        |
| Lint code                     | `make lint`                            |
| Lint with auto-fix            | `make lint-fix`                        |
| Format code                   | `make format`                          |
| Type check                    | `make type-check`                      |
| Security scan                 | `make security`                        |
| All checks                    | `make all-checks`                      |
| **Testing**                   |                                        |
| Run all tests                 | `make test`                            |
| Run tests with coverage       | `make test-cov`                        |
| Run single test               | `pytest tests/test_xxx.py`             |
| **Development**               |                                        |
| Quick check (lint + types)    | `make check`                           |
| Pre-commit checks             | `make pre-commit`                      |
| Full QA                       | `make qa`                              |
| Fix all auto-fixable          | `make fix`                             |
| **Deployment**                |                                        |
| Quick deploy                  | `make deploy-code`                     |
| Release deploy                | `make deploy-release VERSION=x.y.z`   |
| **Services**                  |                                        |
| Check Qdrant                  | `curl http://localhost:6333/health`    |
| Check MLflow                  | `curl http://localhost:5000/health`    |
| Check Redis                   | `docker exec redis redis-cli PING`     |
| **Documentation**             |                                        |
| Serve docs locally            | `make docs-serve`                      |
| Build docs                    | `make docs-build`                      |

---

## 8. Getting Help

- **Issues:** https://github.com/yastman/rag/issues
- **Documentation:** `docs/PIPELINE_OVERVIEW.md` (system architecture)
- **Caching:** `CACHING.md` (Redis 4-tier cache)

---

**Last Updated:** 2025-01-20
