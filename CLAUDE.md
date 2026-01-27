# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

```bash
make check              # Lint + types
make test               # All tests
pytest tests/unit/ -v   # Unit tests only
make docker-up          # Start Qdrant, Redis, MLflow
. venv/bin/activate     # Activate venv
```

## Project Overview

**Contextual RAG Pipeline** - Production RAG system with hybrid search (RRF + ColBERT), Voyage AI embeddings, multi-level caching, and Telegram bot.

**Version:** 2.13.0 | **Python:** 3.12+ | **LLM:** GLM-4 (OpenAI-compatible)
**Use cases:** Ukrainian Criminal Code (1,294 docs), Bulgarian property catalogs (92 docs)

## Current Sprint

**Status:** Complete
**Version:** 2.13.0

### Recently Completed (2026-01-26)
- Test coverage 80% (1105 tests, 82% coverage, 0 failures)
- Parallel workers documentation (spawn-claude)
- Superpowers skills reference (14 skills)
- Binary quantization A/B testing

---
*Updated: 2026-01-26*

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
make e2e-test                              # All 25 tests
make e2e-test-group GROUP=price_filters    # Specific group
python scripts/e2e/runner.py --scenario 3.1  # Single test
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

## Parallel Claude Workers (tmux + spawn-claude)

Запуск нескольких Claude-агентов одновременно для ускорения работы.

### Архитектура

```
tmux session "claude"
├── Окно 1: Основной Claude (оркестратор)
│   └── Создаёт план и запускает воркеров через spawn-claude
├── Окно 2: Worker 1 (независимая Claude сессия)
├── Окно 3: Worker 2 (независимая Claude сессия)
├── Окно 4: Worker 3 (независимая Claude сессия)
└── Окно 5+: Дополнительные воркеры по мере необходимости
```

**Результат:** N Claude-агентов работают **параллельно**, каждый на своей задаче, в одной tmux сессии.

### Быстрый старт (3 шага)

**1. Открыть tmux сессию в проекте**
```bash
cd /mnt/c/Users/user/Documents/Сайты/rag-fresh
tmux new -s claude
# Или через WezTerm (Ctrl+Shift+M) → выбрать проект
```

**2. Запустить основную Claude сессию**
```bash
claude
```

**3. Из Claude запустить воркеров**
```bash
spawn-claude "W1: Task description" "$(pwd)"
spawn-claude "W2: Another task" "$(pwd)"
spawn-claude "W3: Third task" "$(pwd)"
```

### Переключение между воркерами (tmux)

| Комбо | Действие |
|-------|----------|
| `Ctrl+A, 1` | Основной Claude (оркестратор) |
| `Ctrl+A, 2/3/4` | Worker 1/2/3 |
| `Ctrl+A, n/p` | Следующее/предыдущее окно |
| `Ctrl+A, w` | Список всех окон |
| `Ctrl+A, d` | Отсоединиться (session stays) |

### Синтаксис spawn-claude

```bash
spawn-claude "ПРОМПТ" "ПУТЬ"
```

| Параметр | Значение | Пример |
|----------|----------|--------|
| **ПРОМПТ** | Задача для Claude | `"W1: Implement feature X"` |
| **ПУТЬ** | Путь к проекту | `"$(pwd)"` или абсолютный путь |

**ОБЯЗАТЕЛЬНО:** Всегда передавай путь к проекту вторым аргументом.

### Правила параллелизации (ВАЖНО)

**Главный принцип:** 1 воркер = 1 набор независимых файлов. Никогда не делить один файл между воркерами.

| Правило | Хорошо | Плохо |
|---------|--------|-------|
| 1 воркер = 1 модуль | W1: cache.py, W2: qdrant.py | W1: cache.py строки 1-100, W2: cache.py строки 101-200 |
| Группируй мелкое | W1: metrics + otel + eval | W1: metrics, W2: otel, W3: eval (оверхед) |
| Тесты с кодом | W1: auth.py + test_auth.py | W1: auth.py, W2: test_auth.py |
| Общий файл — только чтение | Все читают план | Все пишут в один файл |

### Шаблон промпта для воркера

```bash
spawn-claude "W{N}: {Краткое описание задачи}.

REQUIRED SKILLS:
- superpowers:executing-plans
- superpowers:verification-before-completion

План: docs/plans/YYYY-MM-DD-task.md
Задачи: Task N (секция из плана)

Твои файлы (ТОЛЬКО ЭТИ):
- module.py
- test_module.py

Алгоритм:
1. Прочитай план, найди свои задачи
2. Выполни каждый Step по порядку
3. VERIFY: команда для проверки
4. git commit после каждой задачи
5. НЕ ТРОГАЙ файлы других воркеров" "$(pwd)"
```

### Пример: E2E Testing (4 воркера)

```bash
PROJECT="/mnt/c/Users/user/Documents/Сайты/rag-fresh"

# Worker 1: Test Scenarios
spawn-claude "W1: Task 3 - Test Scenarios.
REQUIRED: superpowers:executing-plans
План: docs/plans/2026-01-27-e2e-bot-testing-impl.md
Задача: Task 3 - создать scripts/e2e/test_scenarios.py
git commit после завершения" $PROJECT

# Worker 2: Telethon Client
spawn-claude "W2: Task 4 - Telethon Client.
REQUIRED: superpowers:executing-plans
План: docs/plans/2026-01-27-e2e-bot-testing-impl.md
Задача: Task 4 - создать scripts/e2e/telegram_client.py" $PROJECT

# Worker 3: Claude Judge
spawn-claude "W3: Task 5 - Claude Judge.
REQUIRED: superpowers:executing-plans
План: docs/plans/2026-01-27-e2e-bot-testing-impl.md
Задача: Task 5 - создать scripts/e2e/claude_judge.py" $PROJECT

# Worker 4: Data Generator + Reports
spawn-claude "W4: Tasks 6+8 - Data Generator + Reports.
REQUIRED: superpowers:executing-plans
План: docs/plans/2026-01-27-e2e-bot-testing-impl.md
Задачи: Task 6 + Task 8" $PROJECT
```

### Мониторинг прогресса

```bash
# git log (обновляется каждые 2 сек)
watch -n 2 "git log --oneline -10"

# Какие файлы изменены
git diff --name-only HEAD~5

# Финальная проверка
. venv/bin/activate && pytest tests/unit/ -q
```

### Обработка ошибок

| Проблема | Решение |
|----------|---------|
| "Not inside tmux session" | `Ctrl+Shift+M` (войти в tmux) или `tmux new -s claude` |
| Worker зависает | `Ctrl+A, {номер}` → `Ctrl+C` → `claude` |
| Конфликт в git | `git status` → `git add .` → `git commit -m "Merge workers"` |

### Шпаргалка tmux

| Комбо | Действие |
|-------|----------|
| `Ctrl+A, c` | Новое окно |
| `Ctrl+A, n/p` | Следующее/предыдущее |
| `Ctrl+A, 1/2/3` | Перейти на окно |
| `Ctrl+A, w` | Список окон |
| `Ctrl+A, d` | Отсоединиться (session stays) |
| `Ctrl+A, \|` | Вертикальный сплит |
| `Ctrl+A, -` | Горизонтальный сплит |

### Когда использовать

**Используй:** много независимых задач (3+), каждому свои файлы, план готов

**Не используй:** зависимые задачи, один файл для всех, нужна координация

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
