# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Contextual RAG Pipeline** - A production-grade Retrieval-Augmented Generation system for document search with hybrid vector search, ML platform integration, and Telegram bot interface.

**Version:** 2.8.0 (95% production-ready)
**Python:** 3.12+ (minimum 3.9)
**Primary use cases:** Ukrainian Criminal Code search (1,294 documents), Bulgarian property catalogs

## Build & Development Commands

```bash
# Install dependencies
make install          # Production deps (pip install -e .)
make install-dev      # Dev tools (ruff, mypy, pytest, etc.)
make install-all      # All deps (prod + dev + docs)

# Code quality
make lint             # Ruff linter check
make lint-fix         # Auto-fix linting issues
make format           # Format with Ruff
make type-check       # MyPy type checking
make security         # Bandit security scan
make check            # Quick check (lint + types)
make fix              # Auto-fix all issues

# Testing
make test             # Run pytest
make test-cov         # Tests with coverage (opens htmlcov/index.html)
pytest tests/test_specific.py -v    # Single test file
pytest tests/ -k "test_name"        # Test by name pattern

# Docker services
make docker-up        # Start Qdrant, Redis, MLflow
make docker-down      # Stop services
make local-up         # docker-compose.local.yml variant

# CI/QA
make pre-commit       # Run all checks before commit
make ci               # Full CI pipeline
make qa               # Full QA (all checks + tests)
```

## Architecture

### Core Pipeline Flow

```
Input (PDF/CSV/DOCX) → Docling Parser → Chunker (1024 chars)
    → BGE-M3 Embeddings (dense+sparse+ColBERT) → Qdrant Storage
    → Hybrid RRF Search + ColBERT Rerank → LLM Contextualization → Response
```

### Key Components

| Module | Purpose |
|--------|---------|
| `src/core/pipeline.py` | RAG pipeline orchestrator |
| `src/retrieval/search_engines.py` | 4 search variants (HybridRRFColBERT is default/best) |
| `src/ingestion/` | Document parsing, chunking, indexing |
| `src/models/embedding_model.py` | Singleton BGE-M3 model (saves 4-6GB RAM) |
| `src/cache/redis_semantic_cache.py` | 4-tier semantic cache |
| `telegram_bot/` | Telegram interface with streaming LLM |

### Search Engine Variants

- **HybridRRFColBERTSearchEngine** (default): Dense + Sparse + ColBERT rerank. Recall@1: 0.94, ~1.0s latency
- **DBSFColBERTSearchEngine**: 7% faster variant for low-latency requirements
- **HybridRRFSearchEngine**: Dense + Sparse without ColBERT
- **BaselineSearchEngine**: Dense only (91.3% Recall@1)

### External Services

| Service | Port | Purpose |
|---------|------|---------|
| Qdrant | 6333 | Vector database |
| Redis Stack | 6379, 8001 | Semantic cache (RediSearch) |
| MLflow | 5000 | Experiment tracking |
| Langfuse | 3001 | LLM tracing |

## Code Patterns

### Async I/O
All I/O operations use async (`httpx.AsyncClient`, `AsyncQdrantClient`). No blocking calls in async context.

### Singleton Models
```python
from src.models.embedding_model import get_bge_m3_model, get_sentence_transformer
model = get_bge_m3_model()  # Reuses single instance, saves 4-6GB RAM
```

### Configuration
Central settings in `src/config/settings.py`. Uses environment variables via `.env` file.

### Error Handling
Graceful degradation - services fail without crashing. Qdrant: 5s timeout with empty results fallback. LLM: fallback answers from search results.

## Code Style

- **Line length:** 100 characters
- **Formatter/Linter:** Ruff (configured in pyproject.toml)
- **Type hints:** Encouraged, MyPy configured
- **Docstrings:** Google style
- **Imports:** Sorted via Ruff isort

### Commit Messages (Conventional Commits)
```
feat(search): add new search variant
fix(cache): resolve race condition
perf(embedding): implement singleton pattern
docs(readme): update architecture section
refactor(pipeline): extract helper function
test(search): add integration tests
chore(deps): update dependencies
```

## Task Management

Check these files for current project status:
- `TODO.md` - Daily task tracking
- `ROADMAP.md` - Strategic plan (4 phases, 16 tasks)
- `CHANGELOG.md` - Version history (Keep a Changelog format)

## Key Documentation

| Document | Content |
|----------|---------|
| `docs/PIPELINE_OVERVIEW.md` | Complete architecture |
| `docs/QDRANT_STACK.md` | Qdrant configuration |
| `CACHING.md` | 4-tier cache architecture |
| `src/evaluation/README.md` | MLflow, Langfuse, RAGAS |

## Environment Setup

1. Copy `.env.example` to `.env`
2. Fill in API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `QDRANT_API_KEY`, `REDIS_PASSWORD`
3. Run `make install-dev`
4. Start services: `make docker-up`

## Testing Notes

- Tests use pytest with `asyncio_mode = "auto"`
- Coverage reports: `make test-cov` generates `htmlcov/index.html`
- Integration tests require Docker services running
- Smoke test: `python src/evaluation/smoke_test.py`
