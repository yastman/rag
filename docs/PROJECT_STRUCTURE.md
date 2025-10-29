***REMOVED*** 📋 PROJECT STRUCTURE - Contextual RAG v2.0.1

> **Полное руководство структуры проекта с описанием каждого модуля**

***REMOVED******REMOVED*** Оглавление
1. [Обзор проекта](***REMOVED***обзор-проекта)
2. [Структура директорий](***REMOVED***структура-директорий)
3. [Основные модули](***REMOVED***основные-модули)
4. [Технологический стек](***REMOVED***технологический-стек)
5. [Рабочий процесс](***REMOVED***рабочий-процесс)
6. [Быстрая справка](***REMOVED***быстрая-справка)

---

***REMOVED******REMOVED*** Обзор проекта

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

***REMOVED******REMOVED*** Структура директорий

```
rag-fresh/
│
├── 📋 ROOT КОНФИГУРАЦИЯ
│   ├── pyproject.toml               ***REMOVED*** Конфигурация проекта, зависимости
│   ├── config.py                    ***REMOVED*** Параметры приложения
│   ├── prompts.py                   ***REMOVED*** Система промптов для LLM
│   ├── .env                         ***REMOVED*** API ключи и URLs (НЕ коммитить!)
│   ├── .env.example                 ***REMOVED*** Пример переменных окружения
│   ├── .pre-commit-config.yaml      ***REMOVED*** Pre-commit хуки (Ruff, MyPy)
│   └── __init__.py                  ***REMOVED*** Package инициализация
│
├── 🔄 CONTEXTUALIZATION & RETRIEVAL
│   ├── contextualize.py             ***REMOVED*** ⭐ Claude API (основной)
│   ├── contextualize_groq_async.py  ***REMOVED*** Groq асинхронная версия
│   ├── contextualize_openai_async.py ***REMOVED*** OpenAI асинхронная версия
│   ├── contextualize_zai.py         ***REMOVED*** Z.AI синхронная версия
│   └── contextualize_zai_async.py   ***REMOVED*** Z.AI асинхронная версия
│
├── 📥 INGESTION & INDEXING
│   ├── ingestion_contextual_kg_fast.py ***REMOVED*** ⭐ Fast версия (оптимизированная)
│   ├── ingestion_contextual_kg.py      ***REMOVED*** Базовая версия
│   ├── pymupdf_chunker.py              ***REMOVED*** PDF parsing + chunking
│   ├── create_collection_enhanced.py   ***REMOVED*** Создание Qdrant коллекции
│   └── create_payload_indexes.py       ***REMOVED*** Создание индексов для payload
│
├── 🧪 TESTING & VALIDATION
│   ├── test_api_quick.py            ***REMOVED*** Быстрый smoke тест
│   ├── test_api_safe.py             ***REMOVED*** Безопасное тестирование
│   ├── test_api_comparison.py       ***REMOVED*** Сравнение разных API
│   ├── test_api_extended.py         ***REMOVED*** Расширенный тест с метриками
│   ├── test_api_comparison_multi.py ***REMOVED*** Multi-API сравнение
│   ├── test_dbsf_fusion.py          ***REMOVED*** Тестирование DBSF+ColBERT
│   ├── evaluate_ab.py               ***REMOVED*** A/B тестирование
│   ├── evaluation.py                ***REMOVED*** Основной evaluator
│   └── example_search.py            ***REMOVED*** Пример использования
│
├── 📊 EVALUATION/
│   ├── search_engines.py            ***REMOVED*** Реализация 3 поисковиков
│   │                                ***REMOVED*** (Baseline, Hybrid, DBSF)
│   ├── run_ab_test.py               ***REMOVED*** ⭐ A/B тест с MLflow логированием
│   ├── evaluate_with_ragas.py       ***REMOVED*** RAGAS framework интеграция
│   ├── smoke_test.py                ***REMOVED*** Smoke тесты
│   ├── langfuse_integration.py      ***REMOVED*** Langfuse (LLM tracing)
│   ├── mlflow_integration.py        ***REMOVED*** MLflow (experiment tracking)
│   ├── evaluator.py                 ***REMOVED*** Основной evaluator класс
│   ├── metrics_logger.py            ***REMOVED*** Логирование метрик
│   ├── config_snapshot.py           ***REMOVED*** Снимок конфигурации при запуске
│   ├── generate_test_queries.py     ***REMOVED*** Генерация тестовых запросов
│   ├── extract_ground_truth.py      ***REMOVED*** Извлечение правильных ответов
│   ├── search_engines_rerank.py     ***REMOVED*** Reranking поисков
│   ├── test_mlflow_ab.py            ***REMOVED*** MLflow тестирование
│   ├── data/                        ***REMOVED*** Тестовые данные
│   ├── evaluation/                  ***REMOVED*** Результаты оценки
│   ├── reports/                     ***REMOVED*** Отчеты об оценке
│   └── results/                     ***REMOVED*** Результаты тестов
│
├── 📚 DOCS/
│   ├── INDEX.md                     ***REMOVED*** Указатель всей документации
│   ├── README.md                    ***REMOVED*** Обзор документации
│   ├── documents/                   ***REMOVED*** Украинские юридические документы
│   │   ├── Конституція України
│   │   ├── Кримінальний кодекс України
│   │   └── Цивільний кодекс України
│   ├── guides/                      ***REMOVED*** Практические руководства
│   │   ├── QUICK_START_DBSF.md
│   │   ├── DEDUPLICATION_GUIDE.md
│   │   └── DOC_LING_RAG_TASKS_2025.md
│   ├── implementation/              ***REMOVED*** Чеклисты и планы
│   │   ├── IMPLEMENTATION_CHECKLIST.md
│   │   └── DBSF_COLBERT_IMPLEMENTATION_SUMMARY.md
│   ├── reports/                     ***REMOVED*** Итоговые отчеты
│   │   ├── FINAL_REPORT_CONTEXTUAL_RAG.md
│   │   ├── FINAL_OPTIMIZATION_REPORT.md
│   │   └── TEST_RESULTS_SUMMARY.md
│   └── archive/                     ***REMOVED*** Старые версии документов
│
├── 🛠️ UTILS/
│   ├── __init__.py                  ***REMOVED*** Package инициализация
│   └── structure_parser.py          ***REMOVED*** Парсер структуры документов
│
├── 📦 rag-fresh.egg-info/      ***REMOVED*** Metadata пакета (auto-generated)
│   ├── PKG-INFO
│   ├── SOURCES.txt
│   ├── dependency_links.txt
│   ├── entry_points.txt
│   ├── requires.txt
│   └── top_level.txt
│
├── 🗂️ ROOT ДОКУМЕНТАЦИЯ
│   ├── README.md                    ***REMOVED*** ⭐ Главная документация
│   ├── ARCHITECTURE.md              ***REMOVED*** Архитектура системы
│   ├── SETUP.md                     ***REMOVED*** Установка и настройка
│   ├── CODE_QUALITY.md              ***REMOVED*** Рекомендации качества кода
│   ├── MIGRATION_PLAN.md            ***REMOVED*** План миграции на ML платформы
│   ├── OPTIMIZATION_PLAN.md         ***REMOVED*** План оптимизации
│   ├── DBSF_vs_RRF_ANALYSIS.md      ***REMOVED*** Анализ методов ranking
│   ├── PHASE1_COMPLETION_SUMMARY.md ***REMOVED*** Завершение Phase 1
│   ├── PHASE2_COMPLETION_SUMMARY.md ***REMOVED*** Завершение Phase 2
│   └── PHASE3_COMPLETION_SUMMARY.md ***REMOVED*** Завершение Phase 3
│
├── 🔐 BACKUP & CACHE
│   ├── contextual_rag_backup_*.tar.gz ***REMOVED*** Резервные копии проекта
│   ├── **/__pycache__/              ***REMOVED*** Python кэш (игнорировать)
│   └── *.egg-info/                  ***REMOVED*** Package metadata (игнорировать)
│
└── 📝 GIT & CI/CD
    ├── .git/                        ***REMOVED*** Git репозиторий
    ├── .gitignore                   ***REMOVED*** Игнорируемые файлы
    ├── docker-compose.yml           ***REMOVED*** Docker сервисы (Qdrant, MLflow, Langfuse)
    └── .github/workflows/           ***REMOVED*** GitHub Actions (если есть)
```

---

***REMOVED******REMOVED*** Основные модули

***REMOVED******REMOVED******REMOVED*** 1. Contextualization Layer (Слой контекстуализации)

| Модуль | Назначение | Статус |
|--------|-----------|--------|
| `contextualize.py` | Claude API с prompt caching | ⭐ Основной |
| `contextualize_groq_async.py` | Groq (быстро) | Альтернатива |
| `contextualize_openai_async.py` | OpenAI GPT | Альтернатива |
| `contextualize_zai*.py` | Z.AI (legacy) | Legacy |

**Функция**: Обогащение контекста документов через LLM перед поиском.

```python
***REMOVED*** Пример использования
from contextualize import contextualize_documents
enriched_docs = contextualize_documents(documents, query)
```

---

***REMOVED******REMOVED******REMOVED*** 2. Ingestion Layer (Слой загрузки)

| Модуль | Назначение | Статус |
|--------|-----------|--------|
| `ingestion_contextual_kg_fast.py` | Fast оптимизированная загрузка | ⭐ Основной |
| `ingestion_contextual_kg.py` | Стандартная загрузка | Fallback |
| `pymupdf_chunker.py` | Парсер PDF с chunking | Утилита |
| `create_collection_enhanced.py` | Создание коллекции | Setup |
| `create_payload_indexes.py` | Индексы для payload | Setup |

**Функция**: Загрузка PDF документов в Qdrant с контекстуализацией.

```python
***REMOVED*** Пример использования
from ingestion_contextual_kg_fast import ingest_documents
ingest_documents(pdf_path, collection_name='legal_documents')
```

---

***REMOVED******REMOVED******REMOVED*** 3. Search & Retrieval (Поиск и извлечение)

**Три уровня поиска**:
1. **Baseline**: BM25 + Dense векторы (стандартный)
2. **Hybrid**: Dense + Sparse (BGE-M3 + ColBERT)
3. **DBSF**: Density-Based Semantic Fusion (оптимальный)

**Метрики улучшения (DBSF vs Baseline)**:
- Recall@1: 91.3% → 94.0% (+2.9%) ✅
- NDCG@10: 0.9619 → 0.9711 (+1.0%) ✅
- MRR: 0.9491 → 0.9636 (+1.5%) ✅

```python
***REMOVED*** Реализация в evaluation/search_engines.py
from evaluation.search_engines import DBSFSearchEngine
engine = DBSFSearchEngine()
results = engine.search(query, top_k=10)
```

---

***REMOVED******REMOVED******REMOVED*** 4. Evaluation Layer (Слой оценки)

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

***REMOVED******REMOVED******REMOVED*** 5. Configuration (Конфигурация)

**config.py** - центральная конфигурация проекта:
```python
API_PROVIDER = 'claude'           ***REMOVED*** 'claude', 'openai', 'groq', 'zai'
VECTOR_DB_URL = 'http://localhost:6333'  ***REMOVED*** Qdrant
COLLECTION_NAME = 'legal_documents'
MODEL_NAME = 'claude-3-5-sonnet-20241022'  ***REMOVED*** Основная модель
EMBEDDING_MODEL = 'BAAI/bge-m3'   ***REMOVED*** 1024-dim vectors
```

---

***REMOVED******REMOVED******REMOVED*** 6. Utility Functions (Утилиты)

| Модуль | Назначение |
|--------|-----------|
| `utils/structure_parser.py` | Парсер структуры документов |
| `check_sparse_vectors.py` | Проверка sparse vectors |
| `list_available_models.py` | Список доступных моделей |
| `example_search.py` | Пример использования API |

---

***REMOVED******REMOVED*** Технологический стек

***REMOVED******REMOVED******REMOVED*** Vector Database
- **Qdrant** v0.13.x
- **Dense Embeddings**: BGE-M3 (1024-dim)
- **Sparse Embeddings**: ColBERT
- **Hybrid Search**: DBSF + RRF

***REMOVED******REMOVED******REMOVED*** LLM APIs
- **Anthropic Claude** 3.5 Sonnet (основной)
- **OpenAI GPT-4** (альтернатива)
- **Groq LLaMA3** (быстрая)
- **Z.AI GLM-4.6** (legacy)

***REMOVED******REMOVED******REMOVED*** ML Platforms
- **MLflow** 2.22.1+ (experiment tracking)
- **Langfuse** 3.0.0+ (LLM observability)
- **RAGAS** 0.2.10+ (RAG evaluation)

***REMOVED******REMOVED******REMOVED*** Code Quality
- **Ruff** 0.14.1 (linting + formatting)
- **MyPy** (type checking)
- **Bandit** (security scanning)
- **Pre-commit** (git hooks)

***REMOVED******REMOVED******REMOVED*** Document Processing
- **PyMuPDF** (PDF parsing)
- **FlagEmbedding** (BGE embeddings)
- **LangChain** (ecosystem utilities)

---

***REMOVED******REMOVED*** Рабочий процесс

***REMOVED******REMOVED******REMOVED*** 1️⃣ Setup & Installation
```bash
***REMOVED*** Клонирование репозитория
git clone <repo>
cd rag-fresh

***REMOVED*** Установка зависимостей
pip install -e .

***REMOVED*** Конфигурация
cp .env.example .env
***REMOVED*** Отредактировать .env с вашими API ключами

***REMOVED*** Запуск Qdrant через Docker
docker compose up -d qdrant

***REMOVED*** (Опционально) Запуск ML платформ
docker compose --profile ml up -d mlflow langfuse
```

***REMOVED******REMOVED******REMOVED*** 2️⃣ Data Ingestion
```bash
***REMOVED*** Создание коллекции
python create_collection_enhanced.py

***REMOVED*** Загрузка документов
python ingestion_contextual_kg_fast.py \
  --pdf-path docs/documents/ \
  --collection legal_documents
```

***REMOVED******REMOVED******REMOVED*** 3️⃣ Testing
```bash
***REMOVED*** Smoke тест
python evaluation/smoke_test.py

***REMOVED*** A/B тестирование (с логированием в MLflow)
python evaluation/run_ab_test.py

***REMOVED*** Быстрый тест API
python test_api_quick.py
```

***REMOVED******REMOVED******REMOVED*** 4️⃣ Production Query
```bash
***REMOVED*** Пример поиска
python example_search.py \
  --query "Які право мають громадяни?" \
  --top-k 10
```

***REMOVED******REMOVED******REMOVED*** 5️⃣ Monitoring & Analysis
```bash
***REMOVED*** MLflow Dashboard
open http://localhost:5000

***REMOVED*** Langfuse Dashboard
open http://localhost:3001
```

---

***REMOVED******REMOVED*** Быстрая справка

***REMOVED******REMOVED******REMOVED*** Основные команды

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

***REMOVED******REMOVED******REMOVED*** Важные файлы для редактирования

| Файл | Когда редактировать |
|------|-------------------|
| `.env` | Добавление API ключей |
| `config.py` | Изменение параметров системы |
| `prompts.py` | Обновление промптов для LLM |
| `pyproject.toml` | Добавление новых зависимостей |
| `.pre-commit-config.yaml` | Изменение качества кода |

***REMOVED******REMOVED******REMOVED*** Возможные проблемы

| Проблема | Решение |
|----------|--------|
| `ConnectionError` к Qdrant | Запустите `docker compose up -d qdrant` |
| `APIError` от Claude | Проверьте `.env` ключ `ANTHROPIC_API_KEY` |
| `ModuleNotFoundError` | Переустановите `pip install -e .` |
| Медленный поиск | Используйте `ingestion_contextual_kg_fast.py` |
| Низкие метрики | Проверьте DBSF конфигурацию в `config.py` |

---

***REMOVED******REMOVED*** Документация по модулям

Детальное описание каждого модуля см. в:
- 📖 **MODULE_GUIDE.md** - Описание всех модулей
- 🚀 **QUICK_START.md** - Пошаговый старт
- 📦 **DEPENDENCIES.md** - Все зависимости
- 🔧 **DEBUGGING_GUIDE.md** - Решение проблем

---

***REMOVED******REMOVED*** Контакты и поддержка

- **Issues**: Создавайте GitHub issues
- **Documentation**: См. `/docs` папку
- **Status**: Production ready ✅

---

**Last Updated**: 2025-10-29
**Version**: 2.0.1
**Maintainer**: Contextual RAG Team
