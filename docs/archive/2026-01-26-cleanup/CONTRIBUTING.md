***REMOVED*** Contributing Guide

> Development workflow for the Contextual RAG project

**Repository:** https://github.com/yastman/rag
**Branch:** main
**Python:** 3.12

---

***REMOVED******REMOVED*** 1. Development Setup (Windows + WSL2)

***REMOVED******REMOVED******REMOVED*** Prerequisites

- **WSL2** with Ubuntu 22.04+
- **Docker Desktop** with WSL2 backend enabled
- **Python 3.12** (via pyenv or system package)
- **Git** 2.40+

***REMOVED******REMOVED******REMOVED*** First-Time Setup

```bash
***REMOVED*** 1. Clone the repository
git clone https://github.com/yastman/rag.git
cd rag

***REMOVED*** 2. Create and activate virtual environment
python3.12 -m venv venv
source venv/bin/activate

***REMOVED*** 3. Install dependencies
pip install -e ".[dev]"      ***REMOVED*** Dev dependencies (linters, pytest)
***REMOVED*** Or for all deps:
pip install -e ".[all]"      ***REMOVED*** Dev + docs

***REMOVED*** 4. Copy environment file
cp .env.example .env
***REMOVED*** Edit .env and add your API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)

***REMOVED*** 5. Start Docker services (Qdrant, Redis, MLflow, Langfuse)
docker compose -f docker-compose.local.yml up -d

***REMOVED*** 6. Install pre-commit hooks
pre-commit install --install-hooks
pre-commit install --hook-type pre-push
```

***REMOVED******REMOVED******REMOVED*** Verify Setup

```bash
***REMOVED*** Check Python version
python --version  ***REMOVED*** Should be 3.12.x

***REMOVED*** Verify services
curl http://localhost:6333/health  ***REMOVED*** Qdrant
curl http://localhost:5000/health  ***REMOVED*** MLflow

***REMOVED*** Run tests
pytest tests/
```

---

***REMOVED******REMOVED*** 2. Daily Workflow

***REMOVED******REMOVED******REMOVED*** Start Services

```bash
***REMOVED*** Start Docker services
make local-up
***REMOVED*** Or: docker compose -f docker-compose.local.yml up -d

***REMOVED*** Activate virtual environment
source venv/bin/activate
```

***REMOVED******REMOVED******REMOVED*** Development Commands

```bash
***REMOVED*** Lint code
make lint                    ***REMOVED*** Check only
make lint-fix                ***REMOVED*** Auto-fix issues

***REMOVED*** Format code
make format                  ***REMOVED*** Format all
make format-check            ***REMOVED*** Check only (CI)

***REMOVED*** Type checking
make type-check              ***REMOVED*** MyPy

***REMOVED*** Run tests
make test                    ***REMOVED*** All tests
make test-cov                ***REMOVED*** With coverage report
pytest tests/test_xxx.py     ***REMOVED*** Single test file

***REMOVED*** All checks at once
make check                   ***REMOVED*** Quick: lint + types
make qa                      ***REMOVED*** Full: lint + types + security + tests
```

***REMOVED******REMOVED******REMOVED*** Before Commit

```bash
***REMOVED*** Option 1: Manual checks
make pre-commit              ***REMOVED*** lint-fix + format + type-check + test

***REMOVED*** Option 2: Pre-commit hooks (automatic)
***REMOVED*** Hooks run automatically on git commit:
***REMOVED***   - Ruff linter (with auto-fix)
***REMOVED***   - Ruff formatter
***REMOVED***   - Trailing whitespace
***REMOVED***   - YAML/TOML/JSON validation
***REMOVED***   - Large file check
```

---

***REMOVED******REMOVED*** 3. Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

***REMOVED******REMOVED******REMOVED*** Format

```
<type>: <description>

- <detail 1>
- <detail 2>

Co-Authored-By: Claude <noreply@anthropic.com>
```

***REMOVED******REMOVED******REMOVED*** Types

| Type       | Description                                        |
|------------|----------------------------------------------------|
| `feat`     | New feature                                        |
| `fix`      | Bug fix                                            |
| `docs`     | Documentation only                                 |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test`     | Adding or updating tests                           |
| `chore`    | Build process, dependencies, configs              |
| `ci`       | CI/CD configuration                                |

***REMOVED******REMOVED******REMOVED*** Examples

```bash
***REMOVED*** Feature
git commit -m "feat: add semantic cache with Redis Vector Search

- Implement 4-tier caching architecture
- Add COSINE similarity with 0.85 threshold

Co-Authored-By: Claude <noreply@anthropic.com>"

***REMOVED*** Bug fix
git commit -m "fix: correct embedding dimension mismatch in Qdrant

- Update vector size from 768 to 1024 for BGE-M3

Co-Authored-By: Claude <noreply@anthropic.com>"

***REMOVED*** Documentation
git commit -m "docs: add contributing guide for local development workflow

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

***REMOVED******REMOVED*** 4. Deploy Instructions

***REMOVED******REMOVED******REMOVED*** Quick Deploy (Code Only)

Use `deploy-code` tag for fast deployments (git pull on server).

```bash
***REMOVED*** Create and push deploy tag
make deploy-code
***REMOVED*** Or manually:
git tag -d deploy-code 2>/dev/null || true
git tag deploy-code
git push origin deploy-code --force
```

***REMOVED******REMOVED******REMOVED*** Release Deploy (Versioned)

Use semantic versioning `v*.*.*` tags for releases.

```bash
***REMOVED*** Create release tag
make deploy-release VERSION=2.6.0
***REMOVED*** Or manually:
git tag v2.6.0
git push origin v2.6.0
```

***REMOVED******REMOVED******REMOVED*** GitHub Actions

Deployments are triggered automatically via GitHub Actions:
- `deploy-code` tag: Quick code sync
- `v*.*.*` tags: Full release deployment

---

***REMOVED******REMOVED*** 5. Code Quality

***REMOVED******REMOVED******REMOVED*** Tools

| Tool    | Purpose              | Command               |
|---------|----------------------|-----------------------|
| Ruff    | Linter + Formatter   | `make lint`, `make format` |
| MyPy    | Type Checker         | `make type-check`     |
| Bandit  | Security Scanner     | `make security`       |
| Vulture | Dead Code Detection  | `make dead-code`      |
| pytest  | Testing Framework    | `make test`           |

***REMOVED******REMOVED******REMOVED*** Configuration

All tools are configured in `pyproject.toml`:

- **Ruff**: Line length 100, Python 3.9+ target
- **MyPy**: Strict mode with `ignore_missing_imports`
- **pytest**: Coverage for `src/`, async mode enabled

***REMOVED******REMOVED******REMOVED*** Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:

1. **Ruff Linter** - Check and auto-fix code issues
2. **Ruff Formatter** - Format code (after linting)
3. **Pre-commit-hooks** - Trailing whitespace, YAML/TOML/JSON validation
4. **Branch Protection** - Warning on direct push to main (pre-push)

---

***REMOVED******REMOVED*** 6. Project Structure

```
contextual_rag/
├── src/                     ***REMOVED*** Core RAG pipeline
│   ├── ingestion/           ***REMOVED***   PDF/CSV/DOCX parsers + Qdrant indexing
│   ├── retrieval/           ***REMOVED***   Hybrid search (RRF/DBSF + ColBERT)
│   ├── cache/               ***REMOVED***   Redis 4-tier cache
│   ├── evaluation/          ***REMOVED***   MLflow + Langfuse + RAGAS
│   ├── governance/          ***REMOVED***   Model Registry
│   ├── security/            ***REMOVED***   PII redaction + budget guards
│   ├── core/                ***REMOVED***   RAG pipeline orchestration
│   └── config/              ***REMOVED***   Configuration management
│
├── telegram_bot/            ***REMOVED*** Telegram bot interface (if exists)
│
├── services/                ***REMOVED*** Docker service configs
│   └── bge-m3-api/          ***REMOVED***   BGE-M3 embedding service
│
├── tests/                   ***REMOVED*** Test suite
│   ├── test_*.py            ***REMOVED***   Integration tests
│   └── data/                ***REMOVED***   Test fixtures
│
├── docs/                    ***REMOVED*** Documentation
│   ├── PIPELINE_OVERVIEW.md ***REMOVED***   System architecture
│   └── implementation/      ***REMOVED***   Implementation details
│
├── deploy/                  ***REMOVED*** Server configuration
│   └── telegram-bot.service ***REMOVED***   Systemd service file
│
├── evaluation/              ***REMOVED*** Evaluation data and reports
│   ├── data/                ***REMOVED***   Test datasets
│   └── reports/             ***REMOVED***   Evaluation results
│
├── scripts/                 ***REMOVED*** Utility scripts
│   ├── qdrant_backup.sh     ***REMOVED***   Backup Qdrant
│   └── qdrant_restore.sh    ***REMOVED***   Restore Qdrant
│
├── data/                    ***REMOVED*** Data files
│   └── demo/                ***REMOVED***   Demo documents
│
├── legacy/                  ***REMOVED*** Deprecated code
│
├── pyproject.toml           ***REMOVED*** Project config (deps, tools)
├── Makefile                 ***REMOVED*** Development commands
├── docker-compose.local.yml ***REMOVED*** Local Docker services
├── .pre-commit-config.yaml  ***REMOVED*** Pre-commit hooks config
├── .env.example             ***REMOVED*** Environment template
└── README.md                ***REMOVED*** Project overview
```

---

***REMOVED******REMOVED*** 7. Useful Commands

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

***REMOVED******REMOVED*** 8. Getting Help

- **Issues:** https://github.com/yastman/rag/issues
- **Documentation:** `docs/PIPELINE_OVERVIEW.md` (system architecture)
- **Caching:** `CACHING.md` (Redis 4-tier cache)

---

**Last Updated:** 2025-01-20
