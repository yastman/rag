---
paths: "Makefile, pyproject.toml, uv.lock, .pre-commit-config.yaml"
---

# Build & Tooling

Project uses **uv** package manager with **Ruff** linter/formatter and **pre-commit** hooks.

## Package Management

| Command | Purpose |
|---------|---------|
| `uv sync` | Install all deps from uv.lock |
| `uv sync --no-dev` | Production only |
| `uv sync --extra voice --extra ingest --extra eval` | CI dependency profile |
| `uv sync --all-extras --all-groups` | Everything (docs, ML, etc.) |
| `uv add package` | Add dependency |
| `uv add --group dev package` | Add dev dependency |
| `uv lock` | Regenerate lock file |
| `uv lock --upgrade` | Upgrade all deps |
| `uv lock --check` | Verify lock file (CI) |

## Makefile: Core Targets

| Target | Command / Effect |
|--------|-----------------|
| `make check` | lint + type-check (pre-commit gate) |
| `make lint` | `ruff check src/` |
| `make type-check` | `mypy src/ telegram_bot/ --ignore-missing-imports` |
| `make format` | `ruff format src/` |
| `make install` | `uv sync --no-dev` |
| `make install-dev` | `uv sync` |
| `make install-all` | `uv sync --all-extras --all-groups` |
| `make lock` | `uv lock` |
| `make update` | `uv lock --upgrade` |
| `make update-pkg PKG=X` | `uv lock --upgrade-package X` |
| `make reinstall` | `rm -rf .venv && uv sync` |
| `make setup-hooks` | Install pre-commit + pre-push hooks |
| `make clean` | Remove caches, .pyc files |

## Makefile: Test Targets

| Target | Runs |
|--------|------|
| `make test` | unit + graph_paths, `-n auto --dist=worksteal`, skip legacy_api + requires_extras |
| `make test-unit` | unit only, `-n auto --dist=worksteal`, skip legacy_api |
| `make test-unit-core` | unit, skip legacy_api + requires_extras + slow |
| `make test-integration` | `tests/integration/test_graph_paths.py`, no Docker |
| `make test-cov` | All tests with coverage (src + telegram_bot), HTML report |
| `make test-nightly` | chaos + smoke + slow unit |
| `make test-store-durations` | Regen `.test_durations` for pytest-split |

## Makefile: Docker Targets

| Target | Profile | Services |
|--------|---------|---------|
| `make docker-up` | (none) | core: postgres, qdrant, redis, docling |
| `make docker-bot-up` | bot | + litellm, bot |
| `make docker-obs-up` | obs | + loki, promtail, alertmanager |
| `make docker-ml-up` | ml | + langfuse, mlflow, clickhouse, minio |
| `make docker-ai-up` | ai | + bge-m3, user-base |
| `make docker-ingest-up` | ingest | + ingestion service |
| `make docker-voice-up` | voice | + livekit, sip, voice-agent |
| `make docker-full-up` | full | all services |
| `make docker-down` | full | stop all |
| `make local-up` | - | redis, qdrant, bge-m3, docling (minimal) |

All compose commands use `docker compose --compatibility -f docker-compose.dev.yml`.

## Pre-commit Hooks

File: `.pre-commit-config.yaml`

| Hook | Purpose |
|------|---------|
| ruff-check (v0.15.1) | Lint + auto-fix |
| ruff-format (v0.15.1) | Code formatting |
| trailing-whitespace | Trim whitespace |
| end-of-file-fixer | Ensure newline |
| check-yaml/toml/json | Syntax check |
| check-added-large-files | Block >1MB |
| check-merge-conflict | Detect conflict markers |
| debug-statements | Detect debugger imports |
| mixed-line-ending (--fix=lf) | Normalize line endings |
| branch-protection | Warn on push to main/master (pre-push, exit 0) |

```bash
make setup-hooks                          # Install (one-time)
uv run pre-commit run --all-files         # Run manually
```

## CI Pipeline (`.github/workflows/ci.yml`)

Single job **checks** (self-hosted runner):

| Step | Command |
|------|---------|
| Ruff lint | `ruff check src/ telegram_bot/ tests/ --output-format=github` |
| Ruff format | `ruff format --check src/ telegram_bot/ tests/` |
| Type check | `mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary` |

Install: `uv sync --frozen` (base deps only).

## Dependencies

### pyproject.toml structure

- **`[project.dependencies]`** — runtime (always installed)
- **`[project.optional-dependencies]`** — ml-local, docs, voice, ingest, eval
- **`[dependency-groups]`** (PEP 735) — dev (installed by default with `uv sync`)

### Key production deps

| Package | Purpose |
|---------|---------|
| `qdrant-client>=1.16.2` | Vector DB |
| `langfuse>=3.14.0` | Observability |
| `voyageai>=0.3.0` | Embeddings + rerank API |
| `langgraph>=1.0.3,<2.0` | RAG state graph |
| `langchain-core>=1.2` | Embeddings ABC |
| `aiogram>=3.25.0` | Telegram bot |
| `aiogram-dialog>=2.4.0` | Dialog UI |
| `asyncpg>=0.31.0` | PostgreSQL (lead scoring) |
| `apscheduler>=3.11.2,<4.0` | Nurturing scheduler |
| `cocoindex>=0.3.28` | Ingestion (ingest extra) |

### Key dev deps (`[dependency-groups].dev`)

| Package | Purpose |
|---------|---------|
| `ruff>=0.6.0` | Linter + formatter |
| `mypy>=1.11.0` | Type checking |
| `pytest>=8.3.0` | Test framework |
| `pytest-xdist>=3.8.0` | Parallel tests |
| `pytest-timeout>=2.4.0` | 30s default timeout |
| `pytest-split>=0.11.0` | CI shard splitting |
| `pytest-httpx>=0.35.0` | HTTP mocking |

## Service-level pyproject.toml

| Service | pyproject.toml | uv.lock |
|---------|---------------|---------|
| Bot | `telegram_bot/pyproject.toml` | `telegram_bot/uv.lock` |
| BGE-M3 | `services/bge-m3-api/pyproject.toml` | `services/bge-m3-api/uv.lock` |
| USER-base | `services/user-base/pyproject.toml` | `services/user-base/uv.lock` |
| Ingestion | `pyproject.toml` (root) | `uv.lock` (root) |

After changing service deps: `cd telegram_bot && uv lock`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Lock file outdated | `uv lock` |
| Pre-commit not running | `make setup-hooks` |
| Dependency conflict | `uv lock --upgrade-package X` |
| CI: import error | Add to `uv sync --extra voice --extra ingest --extra eval` |
