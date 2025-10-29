# 📋 PROJECT STRUCTURE - Contextual RAG v2.0.1

> **Полное руководство структуры проекта с описанием каждого модуля**

## Оглавление
1. [Обзор проекта](#обзор-проекта)
2. [Структура директорий](#структура-директорий)
3. [Основные модули](#основные-модули)
4. [Технологический стек](#технологический-стек)
5. [Рабочий процесс](#рабочий-процесс)
6. [Быстрая справка](#быстрая-справка)

---

## Обзор проекта

**Contextual RAG Pipeline** - это production-ready система поиска и извлечения информации из украинских юридических документов, использующая:
- 🤖 **Гибридный поиск**: Dense (BGE-M3) + Sparse (ColBERT) векторы
- 🔍 **DBSF Ranking**: Density-Based Semantic Fusion для оптимальных результатов
- 📊 **ML Платформы**: MLflow + Langfuse для отслеживания экспериментов
- 🚀 **Множественные LLM**: Claude, OpenAI, Groq, Z.AI
- 📚 **Контекстуализация**: Автоматическое обогащение контекста через Claude API

**Версия**: 2.0.1
**Python**: ≥ 3.9
**Лицензия**: MIT
**Статус**: Production Ready ✅

---

## Структура директорий

```
contextual_rag/
│
├── 📋 ROOT КОНФИГУРАЦИЯ
│   ├── pyproject.toml               # Конфигурация проекта, зависимости
│   ├── config.py                    # Параметры приложения
│   ├── prompts.py                   # Система промптов для LLM
│   ├── .env                         # API ключи и URLs (НЕ коммитить!)
│   ├── .env.example                 # Пример переменных окружения
│   ├── .pre-commit-config.yaml      # Pre-commit хуки (Ruff, MyPy)
│   └── __init__.py                  # Package инициализация
│
├── 🔄 CONTEXTUALIZATION & RETRIEVAL
│   ├── contextualize.py             # ⭐ Claude API (основной)
│   ├── contextualize_groq_async.py  ***REMOVED*** асинхронная версия
│   ├── contextualize_openai_async.py # OpenAI асинхронная версия
│   ├── contextualize_zai.py         # Z.AI синхронная версия
│   └── contextualize_zai_async.py   # Z.AI асинхронная версия
│
├── 📥 INGESTION & INDEXING
│   ├── ingestion_contextual_kg_fast.py # ⭐ Fast версия (оптимизированная)
│   ├── ingestion_contextual_kg.py      # Базовая версия
│   ├── pymupdf_chunker.py              # PDF parsing + chunking
│   ├── create_collection_enhanced.py   # Создание Qdrant коллекции
│   └── create_payload_indexes.py       # Создание индексов для payload
│
├── 🧪 TESTING & VALIDATION
│   ├── test_api_quick.py            # Быстрый smoke тест
│   ├── test_api_safe.py             # Безопасное тестирование
│   ├── test_api_comparison.py       # Сравнение разных API
│   ├── test_api_extended.py         # Расширенный тест с метриками
│   ├── test_api_comparison_multi.py # Multi-API сравнение
│   ├── test_dbsf_fusion.py          # Тестирование DBSF+ColBERT
│   ├── evaluate_ab.py               # A/B тестирование
│   ├── evaluation.py                # Основной evaluator
│   └── example_search.py            # Пример использования
│
├── 📊 EVALUATION/
│   ├── search_engines.py            # Реализация 3 поисковиков
│   │                                # (Baseline, Hybrid, DBSF)
│   ├── run_ab_test.py               # ⭐ A/B тест с MLflow логированием
│   ├── evaluate_with_ragas.py       # RAGAS framework интеграция
│   ├── smoke_test.py                # Smoke тесты
│   ├── langfuse_integration.py      # Langfuse (LLM tracing)
│   ├── mlflow_integration.py        # MLflow (experiment tracking)
│   ├── evaluator.py                 # Основной evaluator класс
│   ├── metrics_logger.py            # Логирование метрик
│   ├── config_snapshot.py           # Снимок конфигурации при запуске
│   ├── generate_test_queries.py     # Генерация тестовых запросов
│   ├── extract_ground_truth.py      # Извлечение правильных ответов
│   ├── search_engines_rerank.py     # Reranking поисков
│   ├── test_mlflow_ab.py            # MLflow тестирование
│   ├── data/                        # Тестовые данные
│   ├── evaluation/                  # Результаты оценки
│   ├── reports/                     # Отчеты об оценке
│   └── results/                     # Результаты тестов
│
├── 📚 DOCS/
│   ├── INDEX.md                     # Указатель всей документации
│   ├── README.md                    # Обзор документации
│   ├── documents/                   # Украинские юридические документы
│   │   ├── Конституція України
│   │   ├── Кримінальний кодекс України
│   │   └── Цивільний кодекс України
│   ├── guides/                      # Практические руководства
│   │   ├── QUICK_START_DBSF.md
│   │   ├── DEDUPLICATION_GUIDE.md
│   │   └── DOC_LING_RAG_TASKS_2025.md
│   ├── implementation/              # Чеклисты и планы
│   │   ├── IMPLEMENTATION_CHECKLIST.md
│   │   └── DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md
│   ├── reports/                     # Итоговые отчеты
│   │   ├── FINAL_REPORT_CONTEXTUAL_RAG.md
│   │   ├── FINAL_OPTIMIZATION_REPORT.md
│   │   └── TEST_RESULTS_SUMMARY.md
│   └── archive/                     # Старые версии документов
│
├── 🛠️ UTILS/
│   ├── __init__.py                  # Package инициализация
│   └── structure_parser.py          # Парсер структуры документов
│
├── 📦 contextual_rag.egg-info/      # Metadata пакета (auto-generated)
│   ├── PKG-INFO
│   ├── SOURCES.txt
│   ├── dependency_links.txt
│   ├── entry_points.txt
│   ├── requires.txt
│   └── top_level.txt
│
├── 🗂️ ROOT ДОКУМЕНТАЦИЯ
│   ├── README.md                    # ⭐ Главная документация
│   ├── ARCHITECTURE.md              # Архитектура системы
│   ├── SETUP.md                     # Установка и настройка
│   ├── CODE_QUALITY.md              # Рекомендации качества кода
│   ├── MIGRATION_PLAN.md            # План миграции на ML платформы
│   ├── OPTIMIZATION_PLAN.md         # План оптимизации
│   ├── DBSF_vs_RRF_ANALYSIS.md      # Анализ методов ranking
│   ├── PHASE1_COMPLETION_SUMMARY.md # Завершение Phase 1
│   ├── PHASE2_COMPLETION_SUMMARY.md # Завершение Phase 2
│   └── PHASE3_COMPLETION_SUMMARY.md # Завершение Phase 3
│
├── 🔐 BACKUP & CACHE
│   ├── contextual_rag_backup_*.tar.gz # Резервные копии проекта
│   ├── **/__pycache__/              # Python кэш (игнорировать)
│   └── *.egg-info/                  # Package metadata (игнорировать)
│
└── 📝 GIT & CI/CD
    ├── .git/                        # Git репозиторий
    ├── .gitignore                   # Игнорируемые файлы
    ├── docker-compose.yml           # Docker сервисы (Qdrant, MLflow, Langfuse)
    └── .github/workflows/           # GitHub Actions (если есть)
```

---

## Основные модули

### 1. Contextualization Layer (Слой контекстуализации)

| Модуль | Назначение | Статус |
|--------|-----------|--------|
| `contextualize.py` | Claude API с prompt caching | ⭐ Основной |
| `contextualize_groq_async.py` | Groq (быстро) | Альтернатива |
| `contextualize_openai_async.py` | OpenAI GPT | Альтернатива |
| `contextualize_zai*.py` | Z.AI (legacy) | Legacy |

**Функция**: Обогащение контекста документов через LLM перед поиском.

```python
# Пример использования
from contextualize import contextualize_documents
enriched_docs = contextualize_documents(documents, query)
```

---

### 2. Ingestion Layer (Слой загрузки)

| Модуль | Назначение | Статус |
|--------|-----------|--------|
| `ingestion_contextual_kg_fast.py` | Fast оптимизированная загрузка | ⭐ Основной |
| `ingestion_contextual_kg.py` | Стандартная загрузка | Fallback |
| `pymupdf_chunker.py` | Парсер PDF с chunking | Утилита |
| `create_collection_enhanced.py` | Создание коллекции | Setup |
| `create_payload_indexes.py` | Индексы для payload | Setup |

**Функция**: Загрузка PDF документов в Qdrant с контекстуализацией.

```python
# Пример использования
from ingestion_contextual_kg_fast import ingest_documents
ingest_documents(pdf_path, collection_name='legal_documents')
```

---

### 3. Search & Retrieval (Поиск и извлечение)

**Три уровня поиска**:
1. **Baseline**: BM25 + Dense векторы (стандартный)
2. **Hybrid**: Dense + Sparse (BGE-M3 + ColBERT)
3. **DBSF**: Density-Based Semantic Fusion (оптимальный)

**Метрики улучшения (DBSF vs Baseline)**:
- Recall@1: 91.3% → 94.0% (+2.9%) ✅
- NDCG@10: 0.9619 → 0.9711 (+1.0%) ✅
- MRR: 0.9491 → 0.9636 (+1.5%) ✅

```python
# Реализация в evaluation/search_engines.py
from evaluation.search_engines import DBSFSearchEngine
engine = DBSFSearchEngine()
results = engine.search(query, top_k=10)
```

---

### 4. Evaluation Layer (Слой оценки)

| Модуль | Назначение |
|--------|-----------|
| `run_ab_test.py` | A/B тест с MLflow логированием |
| `evaluate_with_ragas.py` | RAGAS evaluation framework |
| `smoke_test.py` | Быстрые smoke тесты |
| `langfuse_integration.py` | LLM tracing через Langfuse |
| `mlflow_integration.py` | Experiment tracking через MLflow |

**Интеграции**:
- **MLflow**: http://localhost:5000
- **Langfuse**: http://localhost:3001
- **RAGAS**: RAG evaluation metrics

---

### 5. Configuration (Конфигурация)

**config.py** - центральная конфигурация проекта:
```python
API_PROVIDER = 'claude'           # 'claude', 'openai', 'groq', 'zai'
VECTOR_DB_URL = 'http://localhost:6333'  ***REMOVED***
COLLECTION_NAME = 'legal_documents'
MODEL_NAME = 'claude-3-5-sonnet-20241022'  # Основная модель
EMBEDDING_MODEL = 'BAAI/bge-m3'   # 1024-dim vectors
```

---

### 6. Utility Functions (Утилиты)

| Модуль | Назначение |
|--------|-----------|
| `utils/structure_parser.py` | Парсер структуры документов |
| `check_sparse_vectors.py` | Проверка sparse vectors |
| `list_available_models.py` | Список доступных моделей |
| `example_search.py` | Пример использования API |

---

## Технологический стек

### Vector Database
- **Qdrant** v0.13.x
- **Dense Embeddings**: BGE-M3 (1024-dim)
- **Sparse Embeddings**: ColBERT
- **Hybrid Search**: DBSF + RRF

### LLM APIs
- **Anthropic Claude** 3.5 Sonnet (основной)
- **OpenAI GPT-4** (альтернатива)
- **Groq LLaMA3** (быстрая)
- **Z.AI GLM-4.6** (legacy)

### ML Platforms
- **MLflow** 2.22.1+ (experiment tracking)
- **Langfuse** 3.0.0+ (LLM observability)
- **RAGAS** 0.2.10+ (RAG evaluation)

### Code Quality
- **Ruff** 0.14.1 (linting + formatting)
- **MyPy** (type checking)
- **Bandit** (security scanning)
- **Pre-commit** (git hooks)

### Document Processing
- **PyMuPDF** (PDF parsing)
- **FlagEmbedding** (BGE embeddings)
- **LangChain** (ecosystem utilities)

---

## Рабочий процесс

### 1️⃣ Setup & Installation
```bash
# Клонирование репозитория
git clone <repo>
cd contextual_rag

# Установка зависимостей
pip install -e .

# Конфигурация
cp .env.example .env
# Отредактировать .env с вашими API ключами

# Запуск Qdrant через Docker
docker compose up -d qdrant

# (Опционально) Запуск ML платформ
docker compose --profile ml up -d mlflow langfuse
```

### 2️⃣ Data Ingestion
```bash
# Создание коллекции
python create_collection_enhanced.py

# Загрузка документов
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

### 3️⃣ Testing
```bash
# Smoke тест
python evaluation/smoke_test.py

# A/B тестирование (с логированием в MLflow)
python evaluation/run_ab_test.py

# Быстрый тест API
python test_api_quick.py
```

### 4️⃣ Production Query
```bash
# Пример поиска
python example_search.py \
  --query "Які право мають громадяни?" \
  --top-k 10
```

### 5️⃣ Monitoring & Analysis
```bash
# MLflow Dashboard
open http://localhost:5000

# Langfuse Dashboard
open http://localhost:3001
```

---

## Быстрая справка

### Основные команды

| Команда | Описание |
|---------|---------|
| `python test_api_quick.py` | Быстрый smoke тест |
| `python evaluation/run_ab_test.py` | A/B тест с логированием |
| `python example_search.py --query "..."` | Поиск |
| `ruff check .` | Lint проверка |
| `ruff format .` | Форматирование кода |
| `mypy . --ignore-missing-imports` | Type checking |
| `docker compose up -d` | Запуск Qdrant |
| `docker compose --profile ml up -d` | Запуск ML платформ |

### Важные файлы для редактирования

| Файл | Когда редактировать |
|------|-------------------|
| `.env` | Добавление API ключей |
| `config.py` | Изменение параметров системы |
| `prompts.py` | Обновление промптов для LLM |
| `pyproject.toml` | Добавление новых зависимостей |
| `.pre-commit-config.yaml` | Изменение качества кода |

### Возможные проблемы

| Проблема | Решение |
|----------|--------|
| `ConnectionError` к Qdrant | Запустите `docker compose up -d qdrant` |
| `APIError` от Claude | Проверьте `.env` ключ `ANTHROPIC_API_KEY` |
| `ModuleNotFoundError` | Переустановите `pip install -e .` |
| Медленный поиск | Используйте `ingestion_contextual_kg_fast.py` |
| Низкие метрики | Проверьте DBSF конфигурацию в `config.py` |

---

## Документация по модулям

Детальное описание каждого модуля см. в:
- 📖 **MODULE_GUIDE.md** - Описание всех модулей
- 🚀 **QUICK_START.md** - Пошаговый старт
- 📦 **DEPENDENCIES.md** - Все зависимости
- 🔧 **DEBUGGING_GUIDE.md** - Решение проблем

---

## Контакты и поддержка

- **Issues**: Создавайте GitHub issues
- **Documentation**: См. `/docs` папку
- **Status**: Production ready ✅

---

**Last Updated**: 2025-10-29
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team
