# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Contextual RAG Pipeline** - A production-grade Retrieval-Augmented Generation system for document search with hybrid vector search, ML platform integration, and Telegram bot interface.

**Version:** 2.12.0 (SDK migration for search engines, Binary Quantization, multi-level caching)
**Python:** 3.12+ (minimum 3.9)
**LLM:** zai-glm-4.7 (GLM-4, OpenAI-compatible API, streaming)
**Primary use cases:** Ukrainian Criminal Code search (1,294 documents), Bulgarian property catalogs

## Current Sprint

**Focus:** Documentation System + Binary Quantization
**Version:** 2.12.0
**Started:** 2026-01-26

### Active Work
- Documentation system v2 (Release Please, TODO reset)
- Binary quantization A/B testing (`scripts/test_quantization_ab.py`)

### Recently Completed
- SDK migration for search engines (2026-01-26)
- DBSF fusion implementation
- Query routing (CHITCHAT/SIMPLE/COMPLEX)

### Blockers
None

---
*Updated: 2026-01-26 | Next review: 2026-02-02*

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
    → QueryPreprocessor (translit, RRF weights) → HybridRetrieverService (RRF fusion)
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

| Service                  | Purpose                                                                  |
| ------------------------ | ------------------------------------------------------------------------ |
| `VoyageService`          | **Unified** embeddings + reranking (voyage-4-large/lite, rerank-2.5)     |
| `QdrantService`          | Smart Gateway: RRF fusion, binary quantization, MMR diversity            |
| `RetrieverService`       | Dense vector search in Qdrant with dynamic filters                       |
| `HybridRetrieverService` | RRF fusion search (dense + sparse)                                       |
| `QueryPreprocessor`      | Translit normalization (Latin→Cyrillic), dynamic RRF weights             |
| `QueryAnalyzer`          | LLM-based filter extraction                                              |
| `QueryRouter`            | **2026** Query classification (CHITCHAT/SIMPLE/COMPLEX) for RAG skipping |
| `CacheService`           | Multi-level cache: semantic, rerank, sparse, conversation (Redis)        |
| `SemanticMessageHistory` | Conversation context with vector similarity search                       |
| `UserContextService`     | Extracts user preferences from queries via LLM                           |
| `CESCPersonalizer`       | **Lazy** personalization with marker detection (`is_personalized_query`) |

**Legacy services** (backward compatibility, use VoyageService for new code):

- `VoyageClient`, `VoyageEmbeddingService`, `VoyageRerankerService`

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

| Service     | Port       | Purpose                     |
| ----------- | ---------- | --------------------------- |
| Qdrant      | 6333       | Vector database             |
| Redis Stack | 6379, 8001 | Semantic cache (RediSearch) |
| MLflow      | 5000       | Experiment tracking         |
| Langfuse    | 3001       | LLM tracing                 |

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

Check these files for current project status:

- `TODO.md` - Daily task tracking
- `ROADMAP.md` - Strategic plan (4 phases, 16 tasks)
- `CHANGELOG.md` - Version history (Keep a Changelog format)

## Key Documentation

| Document                                | Content                                                                               |
| --------------------------------------- | ------------------------------------------------------------------------------------- |
| `docs/PIPELINE_OVERVIEW.md`             | Complete architecture                                                                 |
| `docs/QDRANT_STACK.md`                  | Qdrant configuration                                                                  |
| `CACHING.md`                            | 6-tier cache architecture (semantic, rerank, sparse, query, conversation, embeddings) |
| `src/evaluation/README.md`              | MLflow, Langfuse, RAGAS                                                               |
| `telegram_bot/services/query_router.py` | Query classification patterns (CHITCHAT/SIMPLE/COMPLEX)                               |
| `telegram_bot/services/cesc.py`         | CESC personalizer + `is_personalized_query()`                                         |
| `scripts/test_quantization_ab.py`       | Binary quantization A/B testing with precision@k                                      |

## Environment Setup

1. Copy `.env.example` to `.env`
2. Fill in required keys: `VOYAGE_API_KEY`, `OPENAI_API_KEY`, `QDRANT_API_KEY`, `TELEGRAM_BOT_TOKEN`
3. Optional keys: `ANTHROPIC_API_KEY`, `LANGFUSE_*`, `MLFLOW_TRACKING_URI`
4. Voyage AI model config (optional, defaults shown):
   - `VOYAGE_MODEL_DOCS=voyage-4-large`
   - `VOYAGE_MODEL_QUERIES=voyage-4-lite`
   - `VOYAGE_RERANK_MODEL=rerank-2.5`
5. Qdrant quantization config (optional, defaults shown):
   - `QDRANT_USE_QUANTIZATION=true` - Enable binary quantization
   - `QDRANT_QUANTIZATION_RESCORE=true` - Rescore for accuracy
   - `QDRANT_QUANTIZATION_OVERSAMPLING=2.0` - Candidate multiplier
   - `QDRANT_QUANTIZATION_ALWAYS_RAM=true` - Keep quantized in RAM
6. Run `make install-dev`
7. Start services: `docker compose -f docker-compose.dev.yml up -d` (full stack with bot)

## Testing Notes

- Tests use pytest with `asyncio_mode = "auto"` (async tests don't need `@pytest.mark.asyncio`)
- Coverage reports: `make test-cov` generates `htmlcov/index.html`
- Integration tests require Docker services running
- Run single test: `pytest tests/test_file.py::TestClass::test_method -v`

### Test Structure

```
tests/
├── unit/                    # Unit tests (~200 test cases)
│   ├── test_settings.py     # Settings, API validation, defaults
│   ├── test_chunker.py      # DocumentChunker, CSV chunking
│   ├── test_search_engines.py    # All search engine variants
│   ├── test_voyage_service.py    # Embeddings, reranking
│   └── ...
├── smoke/                   # Smoke tests (20 queries, live services)
│   ├── test_preflight.py    ***REMOVED***/Redis config verification
│   ├── test_smoke_routing.py    # Query classification (no deps)
│   ├── test_smoke_cache.py      # Redis cache operations
│   ├── test_smoke_quantization.py  # Binary quantization A/B
│   └── queries.py           # 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX
├── load/                    # Load tests (parallel chats, p95 metrics)
│   ├── test_load_conversations.py  # Parallel chat simulation
│   ├── test_load_redis_eviction.py # LFU eviction behavior
│   ├── metrics_collector.py # p95 latency analysis
│   ├── chat_simulator.py    # 6-message conversation template
│   └── baseline.json        # Regression detection baseline
├── test_voyage*.py          ***REMOVED*** AI integration tests
└── legacy/                  # Deprecated tests
```

### Running Tests

```bash
# All unit tests (fast, no external services needed)
pytest tests/unit/ -v

# Specific module
pytest tests/unit/test_settings.py -v

# With coverage
pytest tests/unit/ --cov=src --cov=telegram_bot --cov-report=term-missing

# Integration tests (require Docker services)
pytest tests/test_voyage*.py -v
pytest tests/test_e2e_pipeline.py -v

# Exclude legacy tests
pytest tests/ --ignore=tests/legacy -v

# Test specific services (after modifications)
pytest tests/unit/test_qdrant_service.py tests/unit/test_cache_service.py -v
```

### Smoke & Load Tests

```bash
# Preflight: verify Qdrant/Redis configuration
make test-preflight        # Checks binary quantization, allkeys-lfu, maxmemory

# Smoke tests (20 queries: 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX)
make test-smoke-routing    # Query routing only (no external deps)
make test-smoke            # Full smoke suite (requires Qdrant/Redis)

# Load tests (parallel chat simulation)
make test-load-ci          # Mocked mode for CI (fast, no deps)
make test-load             # Live services (requires Qdrant/Redis/Voyage)
make test-load-eviction    # Redis LFU eviction behavior

# Full suite
make test-all-smoke-load   # preflight + smoke + load
```

**Environment variables for load tests:**

- `LOAD_USE_MOCKS=1` - Use mocked services (for CI)
- `LOAD_CHAT_COUNT=30` - Number of parallel chats
- `EVICTION_TEST_MB=10` - Redis pressure test volume

**Generated reports:** `reports/preflight.json`, `reports/load_summary.json`, `reports/redis_stats_timeseries.json`

### Test Coverage Targets

| Module                   | Coverage |
| ------------------------ | -------- |
| `src/config/`            | ~90%     |
| `src/ingestion/`         | ~85%     |
| `src/retrieval/`         | ~80%     |
| `telegram_bot/services/` | ~85%     |

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

- `contextual_bulgaria_voyage4` - Bulgarian property data (92 documents, Voyage-4 embeddings, Binary Quantization)
- `legal_documents` - Ukrainian Criminal Code (1,294 documents, BGE-M3 embeddings)

## Deployment

```bash
# Quick deploy (git pull only on server)
make deploy-code

# Release deploy with version tag
make deploy-release VERSION=2.9.1
```
