# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

```bash
make check              # Lint + types
make test               # All tests
make test-redis         # Verify Redis Query Engine
pytest tests/unit/ -v   # Unit tests only
make docker-up          # Start Qdrant, Redis, MLflow
. venv/bin/activate     # Activate venv
```

## Project Overview

**Contextual RAG Pipeline** - Production RAG system with hybrid search (RRF + ColBERT), Voyage AI embeddings, multi-level caching, and Telegram bot.

**Python:** 3.12+ | **LLM:** Cerebras gpt-oss-120b via LiteLLM | **Embeddings:** Voyage AI
**Use cases:** Bulgarian property catalogs (192 docs), Ukrainian Criminal Code (1,294 docs)

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
    → VoyageService Embeddings (voyage-4-large) + FastEmbed BM42 (sparse) → Qdrant Storage
    → QueryPreprocessor (translit, RRF weights) → QdrantService (RRF fusion)
    → VoyageService Rerank (rerank-2.5) → LLM Contextualization → Response
```

### Key Components

| Module                            | Purpose                                              |
| --------------------------------- | ---------------------------------------------------- |
| `src/core/pipeline.py`            | RAG pipeline orchestrator                            |
| `src/retrieval/search_engines.py` | 4 search variants (HybridRRFColBERT is default/best) |
| `src/ingestion/`                  | Document parsing, chunking, indexing                 |
| `telegram_bot/services/`          | Voyage AI unified services (see below)               |
| `telegram_bot/`                   | Telegram interface with streaming LLM                |

### Telegram Bot Services (Voyage AI Unified)

| Service              | Purpose                                                                  |
| -------------------- | ------------------------------------------------------------------------ |
| `VoyageService`      | **Unified** embeddings + reranking (voyage-4-large/lite, rerank-2.5)     |
| `QdrantService`      | Smart Gateway: RRF fusion, binary quantization, MMR diversity            |
| `RetrieverService`   | Dense vector search in Qdrant with dynamic filters                       |
| `QueryPreprocessor`  | Translit normalization (Latin→Cyrillic), dynamic RRF weights             |
| `QueryAnalyzer`      | LLM-based filter extraction                                              |
| `QueryRouter`        | **2026** Query classification (CHITCHAT/SIMPLE/COMPLEX) for RAG skipping |
| `CacheService`       | Multi-level cache: semantic, rerank, sparse, conversation (Redis)        |
| `UserContextService` | Extracts user preferences from queries via LLM                           |
| `CESCPersonalizer`   | **Lazy** personalization with marker detection (`is_personalized_query`) |
| `LLMService`         | LLM interaction with streaming and fallbacks via LiteLLM                 |
| `UserBaseVectorizer` | Local Russian embeddings (deepvk/USER-base, ruMTEB #1)                   |

**Legacy services** (backward compatibility, use VoyageService for new code):

- `EmbeddingService` (use VoyageService instead)

### Search Engine Variants

- **HybridRRFColBERTSearchEngine** (default): Dense + Sparse + ColBERT rerank. Recall@1: 0.94, ~1.0s latency
- **DBSFColBERTSearchEngine**: 7% faster variant for low-latency requirements
- **HybridRRFSearchEngine**: Dense + Sparse without ColBERT
- **BaselineSearchEngine**: Dense only (91.3% Recall@1)

All hybrid engines use Qdrant SDK `query_points()` with nested prefetch (no httpx):

```python
from qdrant_client import models
from src.retrieval.search_engines import lexical_weights_to_sparse

# 2-stage: Dense + Sparse → RRF fusion
response = client.query_points(
    collection_name="...",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="bm42", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=top_k,
)

# 3-stage: Dense + Sparse → RRF → ColBERT rerank
response = client.query_points(
    collection_name="...",
    prefetch=[
        models.Prefetch(
            prefetch=[
                models.Prefetch(query=dense_vector, using="dense", limit=100),
                models.Prefetch(query=sparse_vector, using="bm42", limit=100),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
        ),
    ],
    query=colbert_vectors,
    using="colbert",
    limit=top_k,
)
```

### External Services

| Service     | Port       | Purpose                                         |
| ----------- | ---------- | ----------------------------------------------- |
| Qdrant      | 6333       | Vector database                                 |
| Redis       | 6379       | Semantic cache (Redis 8.4 + Query Engine)       |
| LiteLLM     | 4000       | LLM Gateway (Cerebras → Groq → OpenAI fallback) |
| Langfuse    | 3001       | LLM tracing                                     |
| MLflow      | 5000       | Experiment tracking                             |
| user-base   | 8003       | Local Russian embeddings (deepvk/USER-base)     |

### LLM Gateway (LiteLLM)

```
Bot → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI → Langfuse tracing
```

**Config:** `docker/litellm/config.yaml`

| Model | Provider | Purpose |
|-------|----------|---------|
| `gpt-oss-120b` | Cerebras | Production (reasoning model) |
| `gpt-4o-mini` | Cerebras GLM-4.7 | Dev/Test (fast) |
| `gpt-4o-mini-fallback` | Groq | Fallback 1 |
| `gpt-4o-mini-openai` | OpenAI | Fallback 2 |

**Key setting:** `reasoning_format: hidden` — removes model's internal reasoning from responses.

## Code Patterns

### I/O Patterns

- **Telegram Bot services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient`)
- **Search Engines**: Sync Qdrant SDK (`QdrantClient.query_points()`) with `models.Prefetch` for nested prefetch
- No blocking calls in async context for bot handlers

##***REMOVED***Service (Recommended)

```python
from telegram_bot.services import VoyageService

# Unified service for embeddings + reranking
service = VoyageService(
    api_key="...",
    model_docs="voyage-4-large",     # For document indexing (1024-dim)
    model_queries="voyage-4-lite",   # For queries (asymmetric retrieval)
    model_rerank="rerank-2.5",       # 32K context window
)

# Async methods (recommended)
query_vec = await service.embed_query("search text")
doc_vecs = await service.embed_documents(["doc1", "doc2"])
results = await service.rerank("query", documents, top_k=5)

# Sync wrappers (for non-async code)
query_vec = service.embed_query_sync("search text")
```

### Local Russian Embeddings (UserBaseVectorizer)

```python
from telegram_bot.services import UserBaseVectorizer

# For semantic cache with Russian text optimization
vectorizer = UserBaseVectorizer(
    base_url="http://localhost:8003",  # or http://user-base:8000 in Docker
)

# Async (recommended)
embedding = await vectorizer.aembed("двухкомнатная квартира")

# Sync wrapper
embedding = vectorizer.embed("двухкомнатная квартира")
```

**Environment:** Set `USE_LOCAL_EMBEDDINGS=true` to use USER-base instead of Voyage API for semantic cache.

### Legacy Singleton Pattern

```python
# Legacy BGE-M3 (local model, high RAM)
from src.models.embedding_model import get_bge_m3_model
model = get_bge_m3_model()  # Reuses single instance, saves 4-6GB RAM
```

### Configuration

Central settings in `src/config/settings.py`. Uses environment variables via `.env` file.

### Error Handling

Graceful degradation - services fail without crashing. Qdrant: 5s timeout with empty results fallback. LLM: fallback answers from search results.

### Query Preprocessing (QueryPreprocessor)

```python
from telegram_bot.services import QueryPreprocessor
pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5")
# Returns:
# {
#   "normalized_query": "apartments in Солнечный берег корпус 5",  # Translit
#   "rrf_weights": {"dense": 0.2, "sparse": 0.8},  # Exact query -> favor sparse
#   "cache_threshold": 0.05,  # Strict for queries with IDs
#   "is_exact": True
# }
```

- **Semantic queries** (no IDs): RRF weights 0.6/0.4 (dense favored), cache threshold 0.10
- **Exact queries** (IDs, corpus, floors): RRF weights 0.2/0.8 (sparse favored), cache threshold 0.05

### Query Routing (2026 Best Practice)

```python
from telegram_bot.services import classify_query, QueryType, get_chitchat_response

query_type = classify_query("Привет!")  # Returns QueryType.CHITCHAT
if query_type == QueryType.CHITCHAT:
    response = get_chitchat_response(query)  # Skip RAG entirely

# QueryType.SIMPLE  → Light RAG, skip rerank
# QueryType.COMPLEX → Full RAG + rerank
```

##***REMOVED*** Binary Quantization (2026 Best Practice)

```python
from telegram_bot.services import QdrantService

***REMOVED***Service with quantization (default: enabled)
qdrant = QdrantService(
    url="http://localhost:6333",
    collection_name="documents",
    use_quantization=True,           # 40x faster search
    quantization_rescore=True,       # Maintain accuracy
    quantization_oversampling=2.0,   # Fetch 2x candidates, rescore top_k
)

# A/B testing: disable quantization per-request
results_baseline = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    quantization_ignore=True,  # Skip quantization for this request
)
```

### 2026 Performance Defaults

| Parameter          | Value | Purpose                             |
| ------------------ | ----- | ----------------------------------- |
| `search_top_k`     | 20    | Fewer candidates → faster Qdrant    |
| `use_quantization` | true  | 40x faster, 75% less RAM            |
| `rerank_top_k`     | 3     | Fewer chunks in LLM context         |
| `max_tokens`       | 1024  | Faster generation                   |
| Rerank cache TTL   | 2h    | Skip API calls for repeated queries |

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

**Active tasks:** `TODO.md` (Claude reads automatically)

**Backlog:** GitHub Issues with labels:
- `next` — следующие к работе
- `backlog` — на будущее
- `idea` — идеи

**Useful commands:**
```bash
gh issue list                      # All open issues
gh issue list --label "next"       # Next to work on
gh issue create --title "..." --label "idea"  # New idea
gh issue close N                   # Close issue
```

**Auto-close:** Use `Closes #N` in commit message.

**History:**
- `git log --oneline --grep="feat\|fix"` - Completed tasks
- `CHANGELOG.md` - Auto-generated by Release Please

**Planning:** `docs/plans/*.md` - Design documents

## Key Documentation

| Document                                | Content                                                                               |
| --------------------------------------- | ------------------------------------------------------------------------------------- |
| `docs/PIPELINE_OVERVIEW.md`             | Complete architecture                                                                 |
| `docs/QDRANT_STACK.md`                  | Qdrant configuration                                                                  |
| `docs/PARALLEL-WORKERS.md`              | tmux + spawn-claude parallel execution                                                |
| `docker/litellm/config.yaml`            | LLM Gateway configuration (models, fallbacks, Langfuse)                               |
| `CACHING.md`                            | 6-tier cache architecture (semantic, rerank, sparse, query, conversation, embeddings) |
| `telegram_bot/services/query_router.py` | Query classification patterns (CHITCHAT/SIMPLE/COMPLEX)                               |

## Parallel Claude Workers

Запуск нескольких Claude-агентов для параллельной работы над независимыми задачами.

**Документация:** [docs/PARALLEL-WORKERS.md](docs/PARALLEL-WORKERS.md)

**Короткий синтаксис (из Claude):**
```
/parallel docs/plans/2026-01-28-feature.md
W1: 1,2,5
W2: 3,4
```

Claude понимает: прочитать план, запустить `spawn-claude` для каждого воркера с правильными скиллами. Оркестратор (основной Claude) не делает задачи сам — только коммитит после воркеров.

**Правило:** 1 воркер = 1 набор независимых файлов. Никогда не делить один файл между воркерами.

## Environment Setup

1. Copy `.env.example` to `.env`
2. Fill in required keys:
   - `TELEGRAM_BOT_TOKEN` — Telegram bot
   - `VOYAGE_API_KEY` — Embeddings & rerank
   - `CEREBRAS_API_KEY` — Primary LLM (via LiteLLM)
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` — LLM tracing
3. Optional keys: `GROQ_API_KEY`, `OPENAI_API_KEY` (fallbacks), `ANTHROPIC_API_KEY` (E2E tests)
4. Run `make install-dev`
5. Start services: `docker compose -f docker-compose.dev.yml up -d`

## Testing

```bash
# Unit tests (fast, no Docker needed)
pytest tests/unit/ -v
pytest tests/unit/test_settings.py -v          # Single module
pytest tests/unit/test_file.py::test_method -v # Single test

# With coverage
pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing
make test-cov                                   # Opens htmlcov/index.html

# Integration tests (require Docker services)
pytest tests/test_voyage*.py -v
pytest tests/test_e2e_pipeline.py -v

# Smoke & load tests
make test-preflight        # Verify Qdrant/Redis config
make test-smoke            # 20 queries smoke suite
make test-load             # Parallel chat simulation
```

**Notes:**
- `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`
- Integration tests require: `make docker-up`

## E2E Testing (Telegram Bot)

End-to-end testing with real Telegram bot and Claude Judge evaluation.

### Setup

```bash
# 1. Get Telegram API credentials from https://my.telegram.org
# 2. Add to .env:
#    TELEGRAM_API_ID=12345
#    TELEGRAM_API_HASH=abcdef...
#    ANTHROPIC_API_KEY=sk-ant-...

# 3. Install dependencies and generate test data
make e2e-setup
```

### Running Tests

```bash
make e2e-test                                # All 25 tests
make e2e-test-group GROUP=price_filters      # Specific group
python scripts/e2e/runner.py --scenario 3.1  # Single test
python scripts/e2e/runner.py --skip-judge    # Skip Claude evaluation (no Anthropic credits needed)
```

### Test Groups

| Group | Tests | Description |
|-------|-------|-------------|
| `commands` | 4 | /start, /help, /clear, /stats |
| `chitchat` | 4 | Greetings, thanks, goodbyes |
| `price_filters` | 4 | Price range queries |
| `room_filters` | 4 | Room count queries |
| `location_filters` | 3 | City and distance queries |
| `search` | 3 | Semantic and complex search |
| `edge_cases` | 3 | Empty results, long queries, special chars |

### Reports

Reports saved to `reports/` directory:
- `e2e_YYYY-MM-DD_HH-MM-SS.json` — Machine-readable results
- `e2e_YYYY-MM-DD_HH-MM-SS.html` — Visual report with expandable details

## Telegram Bot (Docker)

```bash
# Start full dev stack (Qdrant, Redis, Langfuse, MLflow, bot)
docker compose -f docker-compose.dev.yml up -d

# Build and restart bot only
docker compose -f docker-compose.dev.yml build bot
docker compose -f docker-compose.dev.yml up -d bot

# Check bot logs
docker logs dev-bot -f

# Verify bot health
docker ps --format "table {{.Names}}\t{{.Status}}" | grep bot
```

Bot connects to: `@test_nika_homes_bot` (configured via `TELEGRAM_BOT_TOKEN`)

Bot responses use Markdown formatting (`parse_mode="Markdown"`).

#***REMOVED*** Collections

- `contextual_bulgaria_voyage4` - Bulgarian property data (192 documents: 92 real + 100 test, Voyage-4 embeddings, Binary Quantization)
  - Test data marked with `is_test_data: true` payload field
  - Test data IDs: 900000-900099
- `legal_documents` - Ukrainian Criminal Code (1,294 documents, BGE-M3 embeddings)

## Deployment

```bash
# Quick deploy (git pull only on server)
make deploy-code

# Release deploy with version tag
make deploy-release VERSION=2.12.0
```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Redis connection refused` | Redis not running | `docker compose up -d redis` |
| `Qdrant timeout` | Collection too large | Enable `use_quantization=True` |
| `LiteLLM unhealthy` | Slow startup | Wait 30s, check `docker logs dev-litellm` |
| `Langfuse invalid credentials` | Wrong keys | Get keys from Langfuse UI → Settings → API Keys |
| `Voyage API 429` | Rate limit | Use `CacheService`, add delays in batch ops |

## API Rate Limits

- **Cerebras**: High throughput, no strict RPM limits. `reasoning_format: hidden` reduces token usage.
- **Voyage AI**: 300 RPM (embeddings), 100 RPM (rerank). Use `CacheService` to reduce calls.
- **Groq/OpenAI** (fallbacks): Standard limits apply, used only when Cerebras fails.
