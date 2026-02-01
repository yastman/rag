# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference

```bash
make check              # Lint + types
make test               # All tests
make test-unit          # Unit tests only (fast, no deps)
make docker-up          # Start Qdrant, Redis, MLflow
. .venv/bin/activate    # Activate venv (created by uv)
```

**Project Location:** `/home/user/projects/rag-fresh` (native WSL2 filesystem)

## Project Overview

**Contextual RAG Pipeline** - Production RAG system with hybrid search (RRF + ColBERT), Voyage AI embeddings, multi-level caching, and Telegram bot.

**Python:** 3.11+ (3.12 recommended) | **LLM:** Cerebras GLM-4.7 via LiteLLM | **Embeddings:** Voyage AI

**Use cases:** Bulgarian property catalogs (192 docs), Ukrainian Criminal Code (1,294 docs)

## Build & Development Commands

```bash
# Install
make install-dev      # Dev tools (ruff, mypy, pytest)

# Quality
make check            # Quick check (lint + types)
make fix              # Auto-fix all issues

# Testing
make test             # Run pytest
make test-cov         # Tests with coverage

# Docker
make docker-up        # Start Qdrant, Redis, MLflow
make docker-down      # Stop services

# CI
make pre-commit       # Run all checks before commit
```

## Architecture

### Core Pipeline Flow

```
Input (PDF/CSV/DOCX) → Docling Parser → Chunker (1024 chars)
    → VoyageService Embeddings + FastEmbed BM42 (sparse) → Qdrant Storage
    → QueryPreprocessor (translit, RRF weights) → QdrantService (RRF fusion)
    → VoyageService Rerank → LLM Contextualization → Response
```

### Key Components

| Module | Purpose |
|--------|---------|
| `src/core/pipeline.py` | RAG pipeline orchestrator |
| `src/retrieval/search_engines.py` | 4 search variants (HybridRRFColBERT default) |
| `src/ingestion/` | Document parsing, chunking, indexing |
| `telegram_bot/services/` | Voyage AI unified services |
| `telegram_bot/` | Telegram interface with streaming LLM |

### External Services (16 containers)

| Service | Port | Purpose |
|---------|------|---------|
| Qdrant | 6333 | Vector database |
| Redis | 6379 | App cache (semantic, rerank, sparse) |
| LiteLLM | 4000 | LLM Gateway (Cerebras → Groq → OpenAI) |
| Langfuse | 3001 | LLM observability v3 |
| user-base | 8003 | Russian embeddings (deepvk/USER-base) |
| bge-m3 | 8000 | BGE-M3 dense+sparse embeddings |
| bm42 | 8002 | BM42 sparse embeddings |
| docling | 5001 | Document parsing (PDF/DOCX) |
| lightrag | 9621 | LightRAG graph service |

Full stack details: `.claude/rules/docker.md`

### Configuration

```python
from src.config.settings import get_settings
settings = get_settings()  # Lazy, validates API keys on first call
```

## Code Style

- **Line length:** 100 characters
- **Formatter/Linter:** Ruff (configured in pyproject.toml)
- **Type hints:** Encouraged, MyPy configured
- **Docstrings:** Google style

### Commit Messages (Conventional Commits)

```
feat(search): add new search variant
fix(cache): resolve race condition
docs(readme): update architecture section
```

## Task Management

**Active tasks:** `TODO.md` | **Backlog:** GitHub Issues (`next`, `backlog`, `idea` labels)

```bash
gh issue list --label "next"    # Next to work on
```

**Auto-close:** Use `Closes #N` in commit message.

## Key Documentation

| Document | Content |
|----------|---------|
| `docs/PIPELINE_OVERVIEW.md` | Complete architecture |
| `docs/QDRANT_STACK.md` | Qdrant configuration |
| `CACHING.md` | 6-tier cache architecture |

## Environment Setup

1. Copy `.env.example` to `.env`
2. Required keys: `TELEGRAM_BOT_TOKEN`, `VOYAGE_API_KEY`, `CEREBRAS_API_KEY`, `LANGFUSE_*`
3. Optional: `GROQ_API_KEY`, `OPENAI_API_KEY` (fallbacks)
4. Run `make install-dev`
5. Start services: `docker compose -f docker-compose.dev.yml up -d`

## Qdrant Collections

- `contextual_bulgaria_voyage` - Bulgarian property (192 docs, Voyage-4, Binary Quantization)
- `legal_documents` - Ukrainian Criminal Code (1,294 docs, BGE-M3)

## Deployment

```bash
make deploy-code                  # Quick deploy (git pull)
make deploy-release VERSION=2.12.0  # Release deploy
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Redis connection refused` | `docker compose up -d redis` |
| `Qdrant timeout` | Enable `use_quantization=True` |
| `LiteLLM unhealthy` | Wait 30s, check `docker logs dev-litellm` |
| `Voyage API 429` | Use `CacheService`, add delays |

## API Rate Limits

- **Cerebras**: High throughput, no strict RPM limits
- **Voyage AI**: 300 RPM (embeddings), 100 RPM (rerank). Use `CacheService`.

## Modular Docs

See `.claude/rules/` for domain-specific documentation:

| File | Scope | Loads when working with |
|------|-------|------------------------|
| `services.md` | VoyageService, QdrantService, Cache patterns | `telegram_bot/services/**/*.py` |
| `search.md` | Search engines, Qdrant query_points | `src/retrieval/**/*.py` |
| `testing.md` | Unit tests, E2E, baseline | `tests/**/*.py` |
| `observability.md` | Langfuse, instrumentation | `telegram_bot/observability.py` |
| `docker.md` | LiteLLM, docker-compose, bot | `docker/**/*` |
