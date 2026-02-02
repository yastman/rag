# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference

```bash
make check              # Lint + types
make test               # All tests
make test-unit          # Unit tests only (fast)
make docker-up          # Start services
. .venv/bin/activate    # Activate venv
```

**Location:** `/home/user/projects/rag-fresh` (WSL2)

## Project Overview

**Contextual RAG Pipeline** — Production RAG with hybrid search (RRF + ColBERT), Voyage AI embeddings, multi-level caching, Telegram bot.

**Stack:** Python 3.12 | Cerebras via LiteLLM | Voyage AI | Qdrant | Redis

**Use cases:** Bulgarian property (192 docs), Ukrainian Criminal Code (1,294 docs)

## Architecture

```
Input → Docling Parser → Chunker → Voyage Embeddings + BM42 → Qdrant
     → QueryPreprocessor → RRF Fusion → Rerank → LLM → Response
```

| Module | Purpose |
|--------|---------|
| `src/core/pipeline.py` | RAG orchestrator |
| `src/retrieval/search_engines.py` | 4 search variants |
| `src/ingestion/` | Parsing, chunking, indexing |
| `telegram_bot/` | Bot + services |

**Services:** Qdrant:6333, Redis:6379, LiteLLM:4000, Langfuse:3001 → see `.claude/rules/docker.md`

## Code Style

- **Line length:** 100 | **Linter:** Ruff | **Types:** MyPy | **Docstrings:** Google style
- **Commits:** `feat(scope): message` | `fix(scope): message` | `docs(scope): message`

## Task Management

**Active:** `TODO.md` | **Backlog:** `gh issue list --label "next"`

**Claude Code Tasks:** Для shared task list между терминалами:
```bash
CLAUDE_CODE_TASK_LIST_ID=my-project claude
```
См. `.claude/rules/shared-tasks.md`

## Environment

1. Copy `.env.example` → `.env`
2. Required: `TELEGRAM_BOT_TOKEN`, `VOYAGE_API_KEY`, `CEREBRAS_API_KEY`, `LANGFUSE_*`
3. `make install-dev && make docker-up`

## Key Docs

| Document | Content |
|----------|---------|
| `docs/PIPELINE_OVERVIEW.md` | Architecture |
| `docs/QDRANT_STACK.md` | Vector DB |
| `CACHING.md` | 6-tier cache |

## Qdrant Collections

- `contextual_bulgaria_voyage` — Bulgarian property (Voyage-4, BQ)
- `legal_documents` — Ukrainian Criminal Code (BGE-M3)

## Deployment

```bash
make deploy-code                    # Quick (git pull)
make deploy-release VERSION=2.12.0  # Release
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Redis connection refused | `docker compose up -d redis` |
| Qdrant timeout | `use_quantization=True` |
| Voyage 429 | Use CacheService |

## Skills Workflow

```
/writing-plans → /executing-plans → /finishing-a-development-branch
```

**Details:** `.claude/rules/skills.md`

## Modular Docs

See `.claude/rules/` for domain-specific documentation:

| File | Scope |
|------|-------|
| `features/caching.md` | 6-tier cache, TTL |
| `features/search-retrieval.md` | Hybrid RRF, Qdrant |
| `features/embeddings.md` | Voyage, BGE-M3, BM42 |
| `features/llm-integration.md` | LiteLLM, fallbacks |
| `features/telegram-bot.md` | Handlers, middlewares |
| `features/ingestion.md` | Parsing, chunking |
| `services.md` | VoyageService, QdrantService |
| `search.md` | Search engines |
| `testing.md` | Unit tests, E2E |
| `docker.md` | Containers, compose |
| `skills.md` | Superpowers workflow |
| `shared-tasks.md` | Multi-terminal tasks |
| `observability.md` | Langfuse |
