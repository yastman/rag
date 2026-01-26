# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Contextual RAG Pipeline** - A production-grade Retrieval-Augmented Generation system for document search with hybrid vector search, ML platform integration, and Telegram bot interface.

**Version:** 2.13.0 (Release Please automation, Binary Quantization, multi-level caching)
**Python:** 3.12+ (minimum 3.9)
**LLM:** zai-glm-4.7 (GLM-4, OpenAI-compatible API, streaming)
**Primary use cases:** Ukrainian Criminal Code search (1,294 documents), Bulgarian property catalogs

## Current Sprint

**Focus:** Binary Quantization A/B Testing
**Version:** 2.13.0
**Started:** 2026-01-26

### Active Work
- Binary quantization A/B testing (`scripts/test_quantization_ab.py`)

### Recently Completed
- Documentation system v2 with Release Please (2026-01-26)
- SDK migration for search engines (2026-01-26)
- DBSF fusion implementation

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

### VoyageService (Recommended)

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

### Qdrant Binary Quantization (2026 Best Practice)

```python
from telegram_bot.services import QdrantService

# QdrantService with quantization (default: enabled)
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

# Smoke & load tests (require Docker services)
make test-preflight        # Verify Qdrant/Redis config
make test-smoke            # 20 queries smoke suite
make test-load             # Parallel chat simulation
```

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

## Qdrant Collections

- `contextual_bulgaria_voyage4` - Bulgarian property data (92 documents, Voyage-4 embeddings, Binary Quantization)
- `legal_documents` - Ukrainian Criminal Code (1,294 documents, BGE-M3 embeddings)

## Deployment

```bash
# Quick deploy (git pull only on server)
make deploy-code

# Release deploy with version tag
make deploy-release VERSION=2.12.0
```

## Parallel Claude Workers (spawn-claude)

Запуск автономных Claude-агентов в отдельных табах WezTerm для ускорения работы.

### Базовый синтаксис

```bash
spawn-claude "промпт" /path/to/project
```

**ОБЯЗАТЕЛЬНО:** Всегда передавай путь к проекту вторым аргументом при вызове из оркестратора.

### Правила параллелизации (ВАЖНО)

**Главный принцип:** 1 воркер = 1 набор независимых файлов. Никогда не делить один файл между воркерами.

| Правило | Хорошо | Плохо |
|---------|--------|-------|
| 1 воркер = 1 модуль | W1: cache.py, W2: qdrant.py | W1: cache.py строки 1-100, W2: cache.py строки 101-200 |
| Группируй мелкое | W1: metrics + otel + eval | W1: metrics, W2: otel, W3: eval (оверхед) |
| Тесты с кодом | W1: auth.py + test_auth.py | W1: auth.py, W2: test_auth.py |
| Общий файл — только чтение | Все читают план, оркестратор обновляет | Все пишут в один файл |

### Количество воркеров

Количество воркеров не ограничено — зависит от сложности задачи и количества независимых файлов.

**Принцип:** 1 независимый набор файлов = 1 воркер. Чем больше независимых частей, тем больше воркеров можно запустить параллельно.

### Архитектура: Оркестратор + Воркеры

```
┌─────────────────────────────────────────────────────┐
│              ОРКЕСТРАТОР (главный Claude)           │
│  - Создаёт план: docs/plans/YYYY-MM-DD-task.md      │
│  - Дробит на независимые задачи                     │
│  - Запускает spawn-claude для каждого воркера       │
│  - Мониторит прогресс                               │
│  - Финальная проверка                               │
└──────────────────────┬──────────────────────────────┘
                       │
     ┌─────────┬───────┴───────┬─────────┐
     ▼         ▼               ▼         ▼
┌────────┐ ┌────────┐     ┌────────┐ ┌────────┐
│Worker 1│ │Worker 2│ ... │Worker N│ │Worker M│
│File: A │ │File: B │     │File: X │ │File: Y │
└────────┘ └────────┘     └────────┘ └────────┘
```

### Шаблон промпта для воркера

```bash
spawn-claude "Ты Worker N. REQUIRED: используй superpowers:executing-plans

План: docs/plans/YYYY-MM-DD-task.md
Задачи: Tasks X.1-X.N (секция Track N)

Твои файлы (ТОЛЬКО ЭТИ):
- module.py
- test_module.py

Алгоритм:
1. Прочитай план, найди свои задачи
2. Выполни каждый Step по порядку
3. git commit после каждой задачи
4. НЕ ТРОГАЙ файлы других воркеров

Команда проверки: . venv/bin/activate && pytest tests/unit/ -q"
```

### Пример: дробление задачи на 6 воркеров

**Задача:** Достичь 80% test coverage для 5 модулей + исправить 22 failing теста

```bash
PROJECT="/mnt/c/Users/user/Documents/Сайты/rag-fresh"

# Worker 1: filter_extractor (свои файлы)
spawn-claude "W1: fix filter_extractor. Files: telegram_bot/services/filter_extractor.py, tests/unit/services/test_filter_extractor.py" $PROJECT

# Worker 2: metrics + otel + evaluator (сгруппированы — мелкие)
spawn-claude "W2: fix metrics_logger + otel + evaluator. Files: tests/unit/test_metrics_logger.py, test_otel_setup.py, test_evaluator.py" $PROJECT

# Worker 3: cache.py (большой модуль — отдельно)
spawn-claude "W3: write cache.py tests to 80%. Files: telegram_bot/services/cache.py, tests/unit/test_cache_service.py" $PROJECT

# Worker 4: user_context.py
spawn-claude "W4: write user_context tests. Files: telegram_bot/services/user_context.py, tests/unit/test_user_context_service.py" $PROJECT

# Worker 5: qdrant + cesc (связанные)
spawn-claude "W5: write qdrant + cesc tests. Files: telegram_bot/services/qdrant.py, cesc.py, tests/unit/test_qdrant_service.py, test_cesc.py" $PROJECT

# Worker 6: query_router
spawn-claude "W6: write query_router tests. Files: telegram_bot/services/query_router.py, tests/unit/test_query_router_full.py" $PROJECT
```

### Автоматический запуск (для оркестратора)

Когда у тебя есть план с независимыми задачами, запускай воркеров через Bash с путём к проекту:

```bash
# Оркестратор выполняет (ОБЯЗАТЕЛЬНО с путём):
spawn-claude "W1: ..." /mnt/c/Users/user/Documents/Сайты/rag-fresh  # → pane 66
spawn-claude "W2: ..." /mnt/c/Users/user/Documents/Сайты/rag-fresh  # → pane 67
spawn-claude "W3: ..." /mnt/c/Users/user/Documents/Сайты/rag-fresh  # → pane 68
# ... и так далее
```

Каждый воркер получит свой терминал в правильной директории проекта.

### Мониторинг прогресса

```bash
# Проверить статус задач
grep -c "\[x\]" docs/plans/*-tasks.md

# Проверить git commits от воркеров
git log --oneline -20

# Финальная проверка
. venv/bin/activate && pytest tests/unit/ -q
```

**Расположение скрипта:** `/mnt/c/Users/user/bin/spawn-claude`

## Superpowers Skills

Скиллы из [obra/superpowers](https://github.com/obra/superpowers). Вызов: `/superpowers:<skill-name>` или через Skill tool.

| Скилл | Когда использовать |
|-------|-------------------|
| `using-superpowers` | **Старт любой задачи.** Проверить какие скиллы применимы перед действием |
| `brainstorming` | **Перед созданием фич.** Превращает идеи в дизайн через диалог |
| `writing-plans` | **Есть спек/требования.** Пишет детальный план до кода (TDD, bite-sized tasks) |
| `executing-plans` | **Есть готовый план.** Выполняет план батчами по 3 задачи с checkpoint'ами |
| `subagent-driven-development` | **План + независимые задачи.** Dispatch субагентов на каждую задачу в текущей сессии |
| `dispatching-parallel-agents` | **2+ независимых задач.** Параллельные агенты без shared state |
| `test-driven-development` | **Любая фича/багфикс.** Тест → fail → минимальный код → pass |
| `systematic-debugging` | **Баг/падающий тест.** Найти root cause ДО попытки исправить |
| `verification-before-completion` | **Перед "готово".** Запустить проверку перед коммитом/PR |
| `requesting-code-review` | **Завершил задачу.** Запросить ревью перед мержем |
| `receiving-code-review` | **Получил фидбек.** Верификация предложений, не слепое согласие |
| `using-git-worktrees` | **Нужна изоляция.** Работа в отдельном worktree без переключения веток |
| `finishing-a-development-branch` | **Код готов.** Выбор: merge / PR / cleanup worktree |
| `writing-skills` | **Создание скилла.** TDD для документации процессов |

**Порядок для новой фичи:**
```
brainstorming → writing-plans → using-git-worktrees → executing-plans/subagent-driven-development → verification-before-completion → requesting-code-review → finishing-a-development-branch
```

**Для дебага:**
```
systematic-debugging → test-driven-development → verification-before-completion
```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Redis connection refused` | Redis not running | `docker compose up -d redis` |
| `Qdrant timeout` | Collection too large or no quantization | Enable `use_quantization=True` |
| `Voyage API 429` | Rate limit exceeded | Add delays in batch operations, use cache |
| `BGE-M3 OOM` | Not using singleton | Use `get_bge_m3_model()` singleton |

## API Rate Limits

- **Voyage AI**: 300 RPM (embeddings), 100 RPM (rerank). Use `CacheService` to reduce calls.
- **GLM-4**: 60 RPM. Streaming enabled by default to improve UX.
