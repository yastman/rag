# Documentation Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Реструктурировать документацию проекта по Diátaxis фреймворку с трекингом задач и статусом local/production.

**Architecture:** Создаём новую структуру docs/ с 8 разделами (status, tasks, context, tutorials, how-to, reference, explanation, archive). Существующий контент мигрируем и консолидируем. Устаревшее переносим в archive/.

**Tech Stack:** Markdown, Git

---

## Task 1: Создание структуры папок

**Files:**
- Create: `docs/status/` (directory)
- Create: `docs/tasks/` (directory)
- Create: `docs/context/` (directory)
- Create: `docs/tutorials/` (directory)
- Create: `docs/how-to/` (directory)
- Create: `docs/reference/` (directory)
- Create: `docs/explanation/` (directory)

**Step 1: Создать все папки**

```bash
mkdir -p docs/status docs/tasks docs/context docs/tutorials docs/how-to docs/reference docs/explanation
```

**Step 2: Проверить создание**

Run: `ls -la docs/`
Expected: Все 7 новых папок + существующие (archive, plans, etc.)

**Step 3: Commit**

```bash
git add docs/
git commit -m "$(cat <<'EOF'
docs: create Diátaxis folder structure

- status/ - project state tracking
- tasks/ - active/todo/done task management
- context/ - Claude Code context files
- tutorials/ - learning-oriented guides
- how-to/ - task-oriented recipes
- reference/ - API and config reference
- explanation/ - architecture concepts

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Создание docs/index.md

**Files:**
- Create: `docs/index.md`

**Step 1: Написать index.md**

```markdown
# Документация Contextual RAG Pipeline

> **Версия:** 2.8.0 | **Статус:** 95% Production-Ready

---

## Быстрый старт

- **Новичок?** Начни с [tutorials/first-search.md](tutorials/first-search.md)
- **Настройка?** Смотри [how-to/setup-local.md](how-to/setup-local.md)
- **Проблемы?** Читай [how-to/troubleshooting.md](how-to/troubleshooting.md)

---

## Навигация

### 📊 Статус проекта
| Документ | Описание |
|----------|----------|
| [status/current-state.md](status/current-state.md) | Что работает (local/prod) |
| [status/local-vs-production.md](status/local-vs-production.md) | Чеклист готовности к prod |

### ✅ Задачи
| Документ | Описание |
|----------|----------|
| [tasks/active.md](tasks/active.md) | В работе сейчас |
| [tasks/todo.md](tasks/todo.md) | Бэклог |
| [tasks/done.md](tasks/done.md) | Выполнено |

### 🎓 Tutorials (Обучение)
| Документ | Описание |
|----------|----------|
| [tutorials/first-search.md](tutorials/first-search.md) | Первый поиск за 5 минут |
| [tutorials/adding-documents.md](tutorials/adding-documents.md) | Добавление документов |

### 🔧 How-To (Рецепты)
| Документ | Описание |
|----------|----------|
| [how-to/setup-local.md](how-to/setup-local.md) | Настройка локально |
| [how-to/deploy-production.md](how-to/deploy-production.md) | Деплой на VPS |
| [how-to/change-llm-provider.md](how-to/change-llm-provider.md) | Смена LLM |
| [how-to/troubleshooting.md](how-to/troubleshooting.md) | Решение проблем |

### 📚 Reference (Справочник)
| Документ | Описание |
|----------|----------|
| [reference/api.md](reference/api.md) | API Reference |
| [reference/configuration.md](reference/configuration.md) | Параметры конфигурации |
| [reference/cli-commands.md](reference/cli-commands.md) | Команды CLI |

### 💡 Explanation (Концепции)
| Документ | Описание |
|----------|----------|
| [explanation/architecture.md](explanation/architecture.md) | Архитектура системы |
| [explanation/hybrid-search.md](explanation/hybrid-search.md) | RRF vs DBSF + ColBERT |

### 🤖 Context (Для Claude Code)
| Документ | Описание |
|----------|----------|
| [context/project-brief.md](context/project-brief.md) | Краткий контекст проекта |
| [context/coding-standards.md](context/coding-standards.md) | Стандарты кода |

---

## Структура по Diátaxis

| Раздел | Цель | Для кого |
|--------|------|----------|
| **tutorials/** | Обучение | Новички |
| **how-to/** | Решение задач | Опытные |
| **reference/** | Справочник | Все |
| **explanation/** | Понимание | Архитекторы |

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/index.md
git commit -m "$(cat <<'EOF'
docs: add main navigation index

- Diátaxis-based structure
- Links to all sections
- Quick start guide

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Создание status/current-state.md

**Files:**
- Create: `docs/status/current-state.md`
- Source: Анализ ROADMAP.md, TODO.md, CHANGELOG.md

**Step 1: Написать current-state.md**

```markdown
# Текущее состояние проекта

> **Версия:** 2.8.0 | **Дата:** 2026-01-21

---

## Статус компонентов

### ✅ Работает локально

| Компонент | Статус | Порт | Примечание |
|-----------|--------|------|------------|
| Qdrant | ✅ Ready | 6333 | docker-compose.local.yml |
| Redis Stack | ✅ Ready | 6379 | С RediSearch для semantic cache |
| BGE-M3 API | ✅ Ready | 8000 | Embeddings service |
| Docling | ✅ Ready | 5001 | Document parsing |
| RAG Pipeline | ✅ Ready | - | src/core/pipeline.py |
| Telegram Bot | ✅ Ready | - | telegram_bot/ |

### ⏳ Требует настройки для Production

| Компонент | Статус | Что нужно |
|-----------|--------|-----------|
| MLflow | ⏳ Partial | Настроить PostgreSQL backend |
| Langfuse | ⏳ Partial | Настроить PostgreSQL + credentials |
| Prometheus | ❌ Not setup | Добавить в docker-compose |
| Grafana | ❌ Not setup | Добавить dashboards |
| SSL/TLS | ❌ Not setup | Nginx reverse proxy |
| Backup | ❌ Not setup | Qdrant snapshots + Redis RDB |

---

## Версии

| Зависимость | Версия | Примечание |
|-------------|--------|------------|
| Python | 3.12.3 | pyproject.toml |
| Qdrant | 1.15.4 (local), 1.16 (dev) | docker-compose |
| Redis Stack | 8.2 | С RediSearch модулем |
| BGE-M3 | latest | BAAI/bge-m3 |
| Aiogram | 3.15.0 | Telegram bot framework |

---

## Метрики качества

| Метрика | Текущее | Цель |
|---------|---------|------|
| Recall@10 | 0.96 | ≥0.95 ✅ |
| NDCG@10 | 0.98 | ≥0.95 ✅ |
| Search latency | ~1.0s | <1.5s ✅ |
| Cache hit rate | 70-80% | >70% ✅ |
| RAM usage | ~6GB | <4GB ⚠️ |

---

## Известные проблемы

1. **RAM usage высокий** — BGE-M3 singleton помогает, но всё ещё ~6GB
2. **Нет distributed lock** — race condition в semantic cache (Task 2.2)
3. **Нет rate limiting** — Telegram bot уязвим к spam (Task 2.3)

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/status/current-state.md
git commit -m "$(cat <<'EOF'
docs: add current project state

- Component status (local/prod)
- Version information
- Quality metrics
- Known issues

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Создание status/local-vs-production.md

**Files:**
- Create: `docs/status/local-vs-production.md`

**Step 1: Написать local-vs-production.md**

```markdown
# Local vs Production: Чеклист готовности

---

## Что работает локально

✅ Всё из docker-compose.local.yml:
- Qdrant (vector database)
- Redis Stack (caching + vector search)
- BGE-M3 API (embeddings)
- Docling (document parsing)

✅ Код:
- RAG Pipeline (src/core/)
- Search Engines (src/retrieval/)
- Telegram Bot (telegram_bot/)
- Ingestion (src/ingestion/)

---

## Чеклист для Production

### 🔴 Critical (блокирует деплой)

- [ ] **Secrets management**
  - [ ] Все API ключи в .env (не в коде!)
  - [ ] .env.server настроен на VPS
  - [ ] Qdrant API key ротирован (был exposed)

- [ ] **Services running**
  - [ ] Qdrant доступен и отвечает
  - [ ] Redis доступен и отвечает
  - [ ] BGE-M3 API загружен и отвечает
  - [ ] Telegram Bot подключен к API

### 🟠 High (нужно для стабильности)

- [ ] **Monitoring**
  - [ ] Логи пишутся в файл (LOG_FILE env var)
  - [ ] JSON формат логов включен
  - [ ] Health checks настроены

- [ ] **Resilience**
  - [ ] Graceful degradation работает
  - [ ] Fallback answers при LLM failure
  - [ ] Timeouts настроены (10s default)

### 🟡 Medium (улучшает надёжность)

- [ ] **Infrastructure**
  - [ ] docker-compose.yml для всех сервисов
  - [ ] Systemd services для auto-restart
  - [ ] Backup strategy для Qdrant

- [ ] **Security**
  - [ ] Rate limiting для bot
  - [ ] SSL/TLS (nginx reverse proxy)
  - [ ] Firewall rules

### 🟢 Nice-to-have

- [ ] **Observability**
  - [ ] MLflow для experiment tracking
  - [ ] Langfuse для LLM tracing
  - [ ] Prometheus metrics
  - [ ] Grafana dashboards

- [ ] **CI/CD**
  - [ ] GitHub Actions для tests
  - [ ] Auto-deploy on tag

---

## Различия окружений

| Аспект | Local | Production |
|--------|-------|------------|
| **Путь** | /mnt/c/.../rag-fresh | /home/admin/contextual_rag |
| **Qdrant** | localhost:6333 | localhost:6333 (или remote) |
| **Redis** | localhost:6379 | localhost:6379 (secure) |
| **Logs** | Console | JSON file |
| **SSL** | Нет | Nginx + Let's Encrypt |
| **Backup** | Нет | Qdrant snapshots |

---

## Команды деплоя

```bash
# На VPS
cd /home/admin/contextual_rag
git pull origin main

# Перезапуск сервисов
sudo systemctl restart telegram-bot

# Проверка статуса
sudo systemctl status telegram-bot
curl localhost:6333/health
```

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/status/local-vs-production.md
git commit -m "$(cat <<'EOF'
docs: add local vs production checklist

- Production readiness checklist
- Environment differences
- Deploy commands

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Создание tasks/active.md

**Files:**
- Create: `docs/tasks/active.md`
- Source: ROADMAP.md (Phase 3 IN PROGRESS)

**Step 1: Написать active.md**

```markdown
# Активные задачи

> Задачи в работе прямо сейчас

---

## В работе

### 📝 Документация

| Задача | Приоритет | Статус |
|--------|-----------|--------|
| Реструктуризация docs/ по Diátaxis | High | 🟡 IN PROGRESS |

---

## Контекст

**Текущая фаза:** Phase 3 (Medium Priority)
**Прогресс фазы:** 20% (1/5 задач)

**Что блокирует:**
- Ничего критического

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/tasks/active.md
git commit -m "$(cat <<'EOF'
docs: add active tasks tracking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Создание tasks/todo.md

**Files:**
- Create: `docs/tasks/todo.md`
- Source: ROADMAP.md, TODO.md

**Step 1: Написать todo.md**

```markdown
# Бэклог задач

> Что нужно сделать (приоритизировано)

---

## 🔴 Critical (Phase 1) — ✅ COMPLETED

Все задачи Phase 1 выполнены в v2.6.0.

---

## 🟠 High Priority (Phase 2)

| # | Задача | Файл | Время | Статус |
|---|--------|------|-------|--------|
| 2.2 | Distributed lock для semantic cache | telegram_bot/services/cache.py | 3h | ⏳ TODO |
| 2.3 | Rate limiting для telegram bot | telegram_bot/bot.py | 3h | ⏳ TODO |
| 2.4 | Proper error handling | Multiple | 6h | ⏳ TODO |

---

## 🟡 Medium Priority (Phase 3)

| # | Задача | Файл | Время | Статус |
|---|--------|------|-------|--------|
| 3.1 | Connection pooling | src/core/client_manager.py | 6h | ⏳ TODO |
| 3.2 | Docker Compose для всех сервисов | docker-compose.yml | 8h | ⏳ TODO |
| 3.3 | CI/CD pipeline (GitHub Actions) | .github/workflows/ | 6h | ⏳ TODO |
| 3.4 | AsyncQdrantClient migration | Multiple | 8h | ⏳ TODO |

---

## 🟢 Nice-to-have (Phase 4)

| # | Задача | Время | Статус |
|---|--------|-------|--------|
| 4.1 | Prometheus metrics | 8h | ⏳ TODO |
| 4.2 | Flat payload structure | 12h | ⏳ TODO |
| 4.3 | Integration tests | 16h | ⏳ TODO |
| 4.4 | Resolve TODOs in evaluation | 8h | ⏳ TODO |

---

## Как взять задачу

1. Выбери задачу из текущей фазы
2. Перенеси в [active.md](active.md)
3. Обнови статус на 🟡 IN PROGRESS
4. После завершения — перенеси в [done.md](done.md)

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/tasks/todo.md
git commit -m "$(cat <<'EOF'
docs: add task backlog

- Prioritized by phase
- Clear time estimates
- Workflow instructions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Создание tasks/done.md

**Files:**
- Create: `docs/tasks/done.md`
- Source: CHANGELOG.md

**Step 1: Написать done.md**

```markdown
# Выполненные задачи

> История завершённых задач

---

## v2.8.0 — Resilience & Observability (2025-01-06)

- ✅ Graceful degradation для всех сервисов
- ✅ Structured JSON logging
- ✅ LLM fallback answers
- ✅ Health checks

## v2.7.0 — User Experience (2025-01-06)

- ✅ Streaming LLM responses (0.1s TTFB)
- ✅ Conversation memory
- ✅ Cross-encoder reranking (+10-15% accuracy)
- ✅ /clear и /stats команды

## v2.6.0 — Critical Fixes (2025-01-06)

- ✅ **1.1** Security: Removed exposed API keys
- ✅ **1.2** Performance: requests → httpx.AsyncClient
- ✅ **1.3** Dependencies: Complete requirements.txt
- ✅ **1.4** Performance: Fixed blocking async calls
- ✅ **2.1** BGE-M3 singleton pattern (saves 4-6GB RAM)

## v2.5.0 — Semantic Cache (2025-11-05)

- ✅ 4-tier caching architecture
- ✅ Redis Vector Search integration
- ✅ 70-80% cache hit rate

## v2.4.0 — Universal Indexer (2025-11-05)

- ✅ CSV/DOCX/XLSX support
- ✅ Demo files organization

## v2.3.0 — DBSF + ColBERT (2025-10-30)

- ✅ Variant B search engine
- ✅ A/B testing framework

## v2.2.0 — RRF + ColBERT (2025-10-30)

- ✅ Variant A search engine (default)
- ✅ BM42 sparse vectors

## v2.1.0 — ML Platform (2025-10-30)

- ✅ MLflow integration
- ✅ Langfuse tracing
- ✅ 2-level Redis cache
- ✅ PII redaction
- ✅ Budget guards

## v2.0.0 — BGE-M3 (2025-10-25)

- ✅ Multi-vector embeddings
- ✅ Qdrant optimizations
- ✅ Int8 quantization

## v1.0.0 — Initial Release (2025-10-15)

- ✅ Basic RAG pipeline
- ✅ PDF parsing
- ✅ Baseline search

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/tasks/done.md
git commit -m "$(cat <<'EOF'
docs: add completed tasks history

- Extracted from CHANGELOG.md
- Organized by version

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Создание context/project-brief.md

**Files:**
- Create: `docs/context/project-brief.md`
- Source: .claude.md (сжатая версия)

**Step 1: Написать project-brief.md**

```markdown
# Project Brief для Claude Code

> Краткий контекст проекта для AI-ассистента

---

## Что это

**Contextual RAG Pipeline** — production система поиска по документам.

**Основной use case:** Поиск по Уголовному кодексу Украины (1,294 документа)

---

## Tech Stack

- **Python 3.12** + asyncio
- **Qdrant** — vector database
- **Redis Stack** — caching + semantic search
- **BGE-M3** — embeddings (dense + sparse + ColBERT)
- **Aiogram 3** — Telegram bot
- **Claude/OpenAI/Groq** — LLM providers

---

## Ключевые модули

```
src/
├── core/pipeline.py      ← RAG оркестратор
├── retrieval/            ← Поисковые движки (RRF, DBSF)
├── ingestion/            ← Парсинг документов
├── cache/                ← Redis 4-tier cache
├── contextualization/    ← LLM интеграции
└── config/               ← Настройки

telegram_bot/             ← Telegram интерфейс
```

---

## Текущий статус

- **Версия:** 2.8.0
- **Готовность:** 95% production-ready
- **Локально:** Всё работает
- **Production:** Требует настройки (см. status/local-vs-production.md)

---

## Правила работы

1. **Читай файл перед редактированием** (обязательно!)
2. **Используй Edit вместо Write** для существующих файлов
3. **Обновляй docs/tasks/** при работе над задачами
4. **Conventional Commits** для сообщений коммитов
5. **Тестируй изменения** перед коммитом

---

## Быстрые ссылки

- [docs/index.md](../index.md) — Навигация
- [docs/tasks/todo.md](../tasks/todo.md) — Что делать
- [docs/status/current-state.md](../status/current-state.md) — Статус

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/context/project-brief.md
git commit -m "$(cat <<'EOF'
docs: add Claude Code project brief

- Compact project context
- Key modules overview
- Quick reference links

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Создание context/coding-standards.md

**Files:**
- Create: `docs/context/coding-standards.md`
- Source: CONTRIBUTING.md, .claude.md

**Step 1: Написать coding-standards.md**

```markdown
# Стандарты кода

---

## Python Style

- **Линтер:** Ruff
- **Длина строки:** 100 символов
- **Кавычки:** Двойные
- **Type hints:** Обязательны
- **Docstrings:** Google style

```python
from typing import Optional

async def search(
    query: str,
    top_k: int = 10,
    filters: Optional[dict] = None
) -> list[SearchResult]:
    """Search for documents.

    Args:
        query: Search query
        top_k: Number of results
        filters: Optional filters

    Returns:
        List of search results
    """
    pass
```

---

## Commits

**Формат:** Conventional Commits

```
<type>(<scope>): <description>
```

**Типы:**
- `feat` — новая функция
- `fix` — исправление бага
- `docs` — документация
- `refactor` — рефакторинг
- `test` — тесты
- `chore` — обслуживание

**Примеры:**
```bash
feat(search): add ColBERT reranking
fix(cache): resolve race condition
docs(readme): update installation guide
```

---

## Git Workflow

1. Работай в feature branch
2. Пиши тесты
3. Запусти `ruff check` и `pytest`
4. Создай PR
5. После merge — удали branch

---

## Файловые операции

1. **Read** файл перед редактированием
2. **Edit** для существующих файлов
3. **Write** только для новых файлов
4. Обновляй документацию при изменениях

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/context/coding-standards.md
git commit -m "$(cat <<'EOF'
docs: add coding standards

- Python style guide
- Commit conventions
- Git workflow

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Создание tutorials/first-search.md

**Files:**
- Create: `docs/tutorials/first-search.md`
- Source: docs/guides/QUICK_START.md

**Step 1: Написать first-search.md**

```markdown
# Первый поиск за 5 минут

> Пошаговое руководство для быстрого старта

---

## Шаг 1: Запуск сервисов

```bash
# Клонируй репозиторий
git clone https://github.com/yastman/rag.git
cd rag

# Запусти Docker сервисы
docker compose -f docker-compose.local.yml up -d

# Проверь что всё работает
curl http://localhost:6333/health  ***REMOVED***
curl http://localhost:6379/ping    # Redis (через docker exec)
```

---

## Шаг 2: Установка зависимостей

```bash
# Создай виртуальное окружение
python3.12 -m venv venv
source venv/bin/activate

# Установи зависимости
pip install -e ".[dev]"

# Скопируй конфигурацию
cp .env.example .env
# Отредактируй .env — добавь API ключи
```

---

## Шаг 3: Первый поиск

```python
# test_search.py
import asyncio
from src.core.pipeline import RAGPipeline

async def main():
    pipeline = RAGPipeline()

    result = await pipeline.search(
        query="Що таке крадіжка?",
        top_k=5
    )

    for doc in result.results:
        print(f"Score: {doc['score']:.3f}")
        print(f"Text: {doc['text'][:200]}...")
        print("---")

asyncio.run(main())
```

```bash
python test_search.py
```

---

## Ожидаемый результат

```
Score: 0.956
Text: Стаття 185. Крадіжка. Таємне викрадення чужого майна (крадіжка)...
---
Score: 0.923
Text: Стаття 186. Грабіж. Відкрите викрадення чужого майна...
---
```

---

## Что дальше?

- [Добавление документов](adding-documents.md)
- [Настройка локально](../how-to/setup-local.md)
- [API Reference](../reference/api.md)

---

**Время:** ~5 минут
```

**Step 2: Commit**

```bash
git add docs/tutorials/first-search.md
git commit -m "$(cat <<'EOF'
docs: add first search tutorial

- Step-by-step guide
- Code examples
- Expected output

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Создание tutorials/adding-documents.md

**Files:**
- Create: `docs/tutorials/adding-documents.md`

**Step 1: Написать adding-documents.md**

```markdown
# Добавление документов

> Как загрузить свои документы в систему

---

## Поддерживаемые форматы

- PDF
- DOCX
- CSV
- XLSX

---

## Шаг 1: Подготовка документов

Положи файлы в папку `data/`:

```bash
data/
├── my_document.pdf
├── data.csv
└── report.docx
```

---

## Шаг 2: Индексация

### PDF документы

```bash
python src/ingestion/indexer.py \
    --input data/my_document.pdf \
    --collection my_documents
```

### CSV данные

```bash
python src/ingestion/csv_to_qdrant.py \
    --input data/data.csv \
    --collection my_data \
    --recreate
```

---

## Шаг 3: Проверка

```python
from qdrant_client import QdrantClient

client = QdrantClient("localhost", port=6333)
info = client.get_collection("my_documents")
print(f"Documents: {info.points_count}")
```

---

## Параметры чанкинга

```python
# В src/ingestion/chunker.py
CHUNK_SIZE = 512      # Размер чанка
CHUNK_OVERLAP = 128   # Перекрытие
```

---

## Что дальше?

- [Поиск по документам](first-search.md)
- [Настройка collection](../reference/configuration.md)

---

**Время:** ~10 минут
```

**Step 2: Commit**

```bash
git add docs/tutorials/adding-documents.md
git commit -m "$(cat <<'EOF'
docs: add document indexing tutorial

- Supported formats
- Indexing commands
- Verification steps

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Создание how-to/setup-local.md

**Files:**
- Create: `docs/how-to/setup-local.md`
- Source: CONTRIBUTING.md, SETUP.md

**Step 1: Написать setup-local.md**

```markdown
# Настройка локального окружения

---

## Требования

- Python 3.12+
- Docker + Docker Compose
- Git
- 8GB RAM (минимум)

---

## Установка

### 1. Клонирование

```bash
git clone https://github.com/yastman/rag.git
cd rag
```

### 2. Python окружение

```bash
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# или: venv\Scripts\activate  # Windows

pip install -e ".[dev]"
```

### 3. Конфигурация

```bash
cp .env.example .env
```

Отредактируй `.env`:

```env
# Обязательно
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key

# Один из LLM провайдеров
ANTHROPIC_API_KEY=sk-ant-...
# или
OPENAI_API_KEY=sk-...
# или
GROQ_API_KEY=gsk_...
```

### 4. Docker сервисы

```bash
docker compose -f docker-compose.local.yml up -d
```

### 5. Проверка

```bash
***REMOVED***
curl http://localhost:6333/health

# Redis
docker exec ai-redis-secure redis-cli PING

# BGE-M3
curl http://localhost:8000/health
```

---

## Ежедневный workflow

```bash
# Запуск сервисов
docker compose -f docker-compose.local.yml up -d

# Активация venv
source venv/bin/activate

# Разработка...

# Линтинг
make lint

# Тесты
make test
```

---

## Проблемы?

См. [troubleshooting.md](troubleshooting.md)

---

**Время:** ~15 минут
```

**Step 2: Commit**

```bash
git add docs/how-to/setup-local.md
git commit -m "$(cat <<'EOF'
docs: add local setup guide

- Prerequisites
- Step-by-step installation
- Daily workflow

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Создание how-to/troubleshooting.md

**Files:**
- Create: `docs/how-to/troubleshooting.md`

**Step 1: Написать troubleshooting.md**

```markdown
# Решение проблем

---

#***REMOVED***

### "Connection refused localhost:6333"

```bash
# Проверь что контейнер запущен
docker ps | grep qdrant

# Если нет — запусти
docker compose -f docker-compose.local.yml up -d qdrant
```

### "Unauthorized" ошибка

```bash
# Проверь API key в .env
cat .env | grep QDRANT_API_KEY

# Должен совпадать с docker-compose
```

---

## Redis

### "Connection refused localhost:6379"

```bash
docker compose -f docker-compose.local.yml up -d redis
```

### "NOAUTH Authentication required"

```bash
# Проверь пароль в .env
REDIS_PASSWORD=your_password
```

---

## BGE-M3

### "Model not loaded"

```bash
# Первый запуск скачивает модель (~7GB)
# Подожди 5-10 минут

# Проверь логи
docker logs ai-bge-m3-api
```

### Out of Memory

```bash
# BGE-M3 требует ~4GB RAM
# Проверь доступную память
free -h
```

---

## Python

### "ModuleNotFoundError"

```bash
# Переустанови зависимости
pip install -e ".[dev]"
```

### "ImportError: cannot import name"

```bash
# Возможно конфликт версий
pip install --upgrade -e ".[dev]"
```

---

## Telegram Bot

### Bot не отвечает

```bash
# Проверь токен в .env
TELEGRAM_BOT_TOKEN=...

# Проверь логи
python telegram_bot/main.py
```

---

## Общие советы

1. **Проверь Docker**: `docker ps`
2. **Проверь логи**: `docker logs <container>`
3. **Проверь .env**: все ключи заполнены?
4. **Перезапусти**: `docker compose restart`

---

**Последнее обновление:** 2026-01-21
```

**Step 2: Commit**

```bash
git add docs/how-to/troubleshooting.md
git commit -m "$(cat <<'EOF'
docs: add troubleshooting guide

- Common issues by component
- Solutions and commands
- General debugging tips

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Создание placeholder файлов

**Files:**
- Create: `docs/how-to/deploy-production.md`
- Create: `docs/how-to/change-llm-provider.md`
- Create: `docs/reference/api.md`
- Create: `docs/reference/configuration.md`
- Create: `docs/reference/cli-commands.md`
- Create: `docs/explanation/architecture.md`
- Create: `docs/explanation/hybrid-search.md`

**Step 1: Создать placeholder файлы**

Каждый файл будет содержать базовую структуру с TODO.

```markdown
# [Title]

> TODO: Мигрировать контент из существующих файлов

---

## Источники для миграции

- [Список файлов-источников]

---

**Статус:** 🔴 TODO
```

**Step 2: Commit**

```bash
git add docs/how-to/ docs/reference/ docs/explanation/
git commit -m "$(cat <<'EOF'
docs: add placeholder files for migration

- how-to: deploy-production, change-llm-provider
- reference: api, configuration, cli-commands
- explanation: architecture, hybrid-search

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Обновление корневого README.md

**Files:**
- Modify: `README.md`

**Step 1: Добавить ссылку на docs/index.md**

В начало README.md добавить:

```markdown
> 📚 **Полная документация:** [docs/index.md](docs/index.md)
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: link to new documentation index

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Финальный коммит

**Step 1: Проверить все изменения**

```bash
git status
git diff --stat HEAD~15
```

**Step 2: Создать summary коммит (если нужен)**

```bash
git log --oneline -15
```

---

## Summary

**Создано файлов:** 15
**Папок:** 7

**Структура:**
```
docs/
├── index.md ✅
├── status/
│   ├── current-state.md ✅
│   └── local-vs-production.md ✅
├── tasks/
│   ├── active.md ✅
│   ├── todo.md ✅
│   └── done.md ✅
├── context/
│   ├── project-brief.md ✅
│   └── coding-standards.md ✅
├── tutorials/
│   ├── first-search.md ✅
│   └── adding-documents.md ✅
├── how-to/
│   ├── setup-local.md ✅
│   ├── troubleshooting.md ✅
│   ├── deploy-production.md (placeholder)
│   └── change-llm-provider.md (placeholder)
├── reference/
│   ├── api.md (placeholder)
│   ├── configuration.md (placeholder)
│   └── cli-commands.md (placeholder)
└── explanation/
    ├── architecture.md (placeholder)
    └── hybrid-search.md (placeholder)
```

---

**План готов!**
