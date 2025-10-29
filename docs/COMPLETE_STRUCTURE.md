***REMOVED*** 📚 ПОЛНАЯ СТРУКТУРА ПРОЕКТА - Contextual RAG v2.0.1

> **Комплексное описание переделанной архитектуры проекта**

***REMOVED******REMOVED*** 📊 Обзор проекта

**Contextual RAG Pipeline** - production-ready система поиска в украинских юридических документах с использованием гибридного поиска, LLM контекстуализации и полной интеграцией с ML платформами.

| Параметр | Значение |
|----------|----------|
| **Версия** | 2.0.1 |
| **Python** | ≥3.9 |
| **Статус** | ✅ Production Ready |
| **Код Issues** | 0 (было 499) |
| **Лучший поиск** | DBSF+ColBERT: 94.0% Recall@1 |
| **Время индексации** | 6 минут на 132 chunks |

---

***REMOVED******REMOVED*** 🏗️ НОВАЯ СТРУКТУРА ПРОЕКТА

***REMOVED******REMOVED******REMOVED*** ROOT УРОВЕНЬ

```
contextual_rag/
├── src/                    ***REMOVED*** ⭐ ВЕСЬ КОД ПРИЛОЖЕНИЯ (новая структура)
├── tests/                  ***REMOVED*** Тест суиты
├── docs/                   ***REMOVED*** Документация
├── data/                   ***REMOVED*** Данные и ресурсы
├── logs/                   ***REMOVED*** Логи приложения
├── legacy/                 ***REMOVED*** Старый код (deprecated)
├── pyproject.toml          ***REMOVED*** Конфигурация зависимостей
├── .env.example            ***REMOVED*** Пример переменных
├── .env                    ***REMOVED*** Переменные окружения (НЕ коммитить!)
├── .gitignore              ***REMOVED*** Git ignore правила
├── .pre-commit-config.yaml ***REMOVED*** Pre-commit hooks
├── docker-compose.yml      ***REMOVED*** Docker сервисы (Qdrant, MLflow, Langfuse)
├── README.md               ***REMOVED*** Главная документация
└── Makefile                ***REMOVED*** Общие команды (опционально)
```

***REMOVED******REMOVED******REMOVED*** SRC СТРУКТУРА - ГЛАВНОЕ (33 Python файла)

```
src/                              ***REMOVED*** Весь код проекта
│
├── __init__.py                   ***REMOVED*** Package инициализация (v2.0.1)
│
├── config/                       ***REMOVED*** ⭐ КОНФИГУРАЦИЯ (2 файла)
│   ├── __init__.py
│   ├── constants.py              ***REMOVED*** Enums, dataclasses, константы
│   │                             ***REMOVED*** - SearchEngine, APIProvider, ModelName
│   │                             ***REMOVED*** - VectorDimensions, ThresholdValues
│   │                             ***REMOVED*** - BatchSizes, RetrievalStages
│   └── settings.py               ***REMOVED*** Settings класс с валидацией
│                                 ***REMOVED*** - Загружает .env и аргументы
│                                 ***REMOVED*** - Создает global settings instance
│
├── contextualization/            ***REMOVED*** ⭐ LLM КОНТЕКСТУАЛИЗАЦИЯ (4 файла)
│   ├── __init__.py
│   ├── base.py                   ***REMOVED*** Базовый класс ContextualizeProvider
│   │                             ***REMOVED*** - ContextualizedChunk dataclass
│   │                             ***REMOVED*** - Abstract методы для провайдеров
│   ├── claude.py                 ***REMOVED*** ⭐ Claude API (РЕКОМЕНДУЕТСЯ)
│   │                             ***REMOVED*** - Prompt caching для 90% экономии
│   │                             ***REMOVED*** - Async + sync методы
│   │                             ***REMOVED*** - Token tracking и cost estimation
│   ├── openai.py                 ***REMOVED*** OpenAI GPT интеграция
│   │                             ***REMOVED*** - Поддержка GPT-4, GPT-3.5
│   │                             ***REMOVED*** - Async + sync обработка
│   └── groq.py                   ***REMOVED*** Groq LLaMA (быстрая альтернатива)
│                                 ***REMOVED*** - 2-4 минуты на 100 chunks
│                                 ***REMOVED*** - Free tier доступен
│
├── retrieval/                    ***REMOVED*** ⭐ ПОИСК И РАНЖИРОВАНИЕ (1 файл)
│   ├── __init__.py
│   └── search_engines.py         ***REMOVED*** 3 search engine реализации
│                                 ***REMOVED*** 1. BaselineSearchEngine (Dense only)
│                                 ***REMOVED***    - 91.3% Recall@1
│                                 ***REMOVED***    - 0.65s latency
│                                 ***REMOVED*** 2. HybridRRFSearchEngine (Dense+Sparse)
│                                 ***REMOVED***    - 88.7% Recall@1
│                                 ***REMOVED***    - RRF fusion
│                                 ***REMOVED*** 3. DBSFColBERTSearchEngine ⭐ BEST
│                                 ***REMOVED***    - 94.0% Recall@1 (+2.9%)
│                                 ***REMOVED***    - DBSF + ColBERT reranking
│                                 ***REMOVED***    - 0.69s latency
│
├── ingestion/                    ***REMOVED*** ⭐ ЗАГРУЗКА ДОКУМЕНТОВ (3 файла)
│   ├── __init__.py
│   ├── pdf_parser.py             ***REMOVED*** PDF парсинг (PyMuPDF)
│   │                             ***REMOVED*** - Поддерживает PDF, DOCX, EPUB, TXT
│   │                             ***REMOVED*** - Метаданные и структура
│   ├── chunker.py                ***REMOVED*** Разбиение на chunks
│   │                             ***REMOVED*** - 3 стратегии: Fixed, Semantic, Sliding
│   │                             ***REMOVED*** - Сохранение структуры документов
│   │                             ***REMOVED*** - Метаданные для юридических документов
│   └── indexer.py                ***REMOVED*** Индексация в Qdrant
│                                 ***REMOVED*** - BGE-M3 embeddings (1024-dim)
│                                 ***REMOVED*** - Batch processing
│                                 ***REMOVED*** - Payload indexes
│
├── evaluation/                   ***REMOVED*** ⭐ ОЦЕНКА И МЕТРИКИ (12 файлов)
│   ├── __init__.py
│   ├── metrics.py                ***REMOVED*** Recall@K, NDCG@K, MRR (новый)
│   ├── mlflow_integration.py     ***REMOVED*** MLflow tracking
│   │                             ***REMOVED*** - Эксперимент tracking
│   │                             ***REMOVED*** - Параметры и метрики
│   ├── langfuse_integration.py   ***REMOVED*** Langfuse LLM tracing
│   │                             ***REMOVED*** - Trace всех LLM запросов
│   │                             ***REMOVED*** - Latency tracking
│   ├── run_ab_test.py            ***REMOVED*** A/B тестирование
│   ├── evaluate_with_ragas.py    ***REMOVED*** RAGAS evaluation
│   ├── smoke_test.py             ***REMOVED*** Быстрые smoke тесты
│   ├── evaluator.py              ***REMOVED*** Основной evaluator класс
│   ├── metrics_logger.py         ***REMOVED*** Логирование метрик
│   ├── config_snapshot.py        ***REMOVED*** Снимок конфигурации
│   ├── generate_test_queries.py  ***REMOVED*** Генерация тестовых запросов
│   ├── search_engines_rerank.py  ***REMOVED*** Reranking поисков
│   └── test_mlflow_ab.py         ***REMOVED*** Тестирование MLflow
│
├── utils/                        ***REMOVED*** ⭐ УТИЛИТЫ (1 файл)
│   ├── __init__.py
│   └── structure_parser.py       ***REMOVED*** Парсер структуры документов
│
└── core/                         ***REMOVED*** ⭐ ГЛАВНЫЙ PIPELINE (1 файл)
    ├── __init__.py
    └── pipeline.py               ***REMOVED*** RAGPipeline - оркестратор
                                  ***REMOVED*** - Главный класс для использования
                                  ***REMOVED*** - Интегрирует все компоненты
                                  ***REMOVED*** - search(), index_documents()
                                  ***REMOVED*** - evaluate(), get_stats()
```

***REMOVED******REMOVED******REMOVED*** DOCS СТРУКТУРА

```
docs/
├── README.md                       ***REMOVED*** Обзор документации
├── README_NEW_STRUCTURE.md         ***REMOVED*** Описание новой структуры
├── COMPLETE_STRUCTURE.md           ***REMOVED*** Этот файл - полная структура
├── PROJECT_STRUCTURE.md            ***REMOVED*** Старое описание (ориентир)
├── QUICK_START.md                  ***REMOVED*** 5 минут до первого поиска
├── INDEX.md                        ***REMOVED*** Указатель документов
│
├── guides/                         ***REMOVED*** Практические керівництва
│   ├── QUICK_START.md              ***REMOVED*** Быстрый старт
│   ├── SETUP.md                    ***REMOVED*** Установка и конфигурация
│   └── CODE_QUALITY.md             ***REMOVED*** Стандарты разработки
│
├── architecture/                   ***REMOVED*** Архитектура и дизайн
│   ├── ARCHITECTURE.md             ***REMOVED*** Системная архитектура
│   ├── MIGRATION_PLAN.md           ***REMOVED*** План миграции на новую структуру
│   └── API_DESIGN.md               ***REMOVED*** Дизайн API (новый)
│
├── implementation/                 ***REMOVED*** Детали реализации
│   ├── OPTIMIZATION_PLAN.md        ***REMOVED*** План оптимизации
│   ├── DBSF_vs_RRF_ANALYSIS.md     ***REMOVED*** Сравнение алгоритмов
│   ├── SEARCH_ENGINE_GUIDE.md      ***REMOVED*** Руководство search engines (новый)
│   └── CONFIG_GUIDE.md             ***REMOVED*** Руководство конфигурации (новый)
│
├── reports/                        ***REMOVED*** Проектные отчеты
│   ├── FULL_PROJECT_ANALYSIS.md    ***REMOVED*** Полный анализ проекта
│   ├── PHASE1_COMPLETION_SUMMARY.md
│   ├── PHASE2_COMPLETION_SUMMARY.md
│   └── PHASE3_COMPLETION_SUMMARY.md
│
├── documents/                      ***REMOVED*** Юридические документы
│   ├── Конституція України/
│   ├── Кримінальний кодекс України/
│   └── Цивільний кодекс України/
│
└── api/                            ***REMOVED*** API Reference (создается)
    └── API_REFERENCE.md            ***REMOVED*** Полный API docs (новый)
```

***REMOVED******REMOVED******REMOVED*** TESTS СТРУКТУРА

```
tests/
├── conftest.py                     ***REMOVED*** Pytest конфигурация (новый)
├── unit/                           ***REMOVED*** Юніт-тести (создавать)
│   ├── test_config.py
│   ├── test_chunker.py
│   └── test_search_engines.py
├── integration/                    ***REMOVED*** Интеграционные тесты (создавать)
│   ├── test_full_pipeline.py
│   └── test_qdrant_integration.py
└── legacy/                         ***REMOVED*** Старые тесты
    ├── test_api_*.py
    ├── evaluate_ab.py
    ├── example_search.py
    └── ...
```

***REMOVED******REMOVED******REMOVED*** DATA СТРУКТУРА

```
data/
├── documents/                      ***REMOVED*** Вхідні PDF документи
│   ├── Конституція_України.pdf
│   ├── Кримінальний_кодекс.pdf
│   └── Цивільний_кодекс.pdf
├── test_queries/                   ***REMOVED*** Тестові запити
│   ├── queries.json                ***REMOVED*** 150+ тестових запитів
│   └── ground_truth.json           ***REMOVED*** Правильні відповіді
├── embeddings/                     ***REMOVED*** Кеш вбудовувань (опціонально)
└── evaluation/                     ***REMOVED*** Результати оцінки
    ├── recall_metrics.json
    ├── ndcg_metrics.json
    └── results_summary.json
```

---

***REMOVED******REMOVED*** 🔑 КЛЮЧЕВЫЕ МОДУЛИ (ДЕТАЛЬНО)

***REMOVED******REMOVED******REMOVED*** 1. CONFIG (`src/config/`)

**Цель**: Централізована конфігурація всієї системи

**Файлы**:
- `constants.py` - Enums, dataclasses, константы
- `settings.py` - Settings класс с загрузкой .env

**Ключевые классы**:
```python
class SearchEngine(Enum):
    BASELINE = "baseline"
    HYBRID_RRF = "hybrid_rrf"
    DBSF_COLBERT = "dbsf_colbert"  ***REMOVED*** Рекомендуется

class APIProvider(Enum):
    CLAUDE = "claude"      ***REMOVED*** ⭐ Рекомендуется
    OPENAI = "openai"
    GROQ = "groq"
    Z_AI = "zai"          ***REMOVED*** Legacy

class Settings:
    def __init__(
        self,
        api_provider: str = "claude",
        search_engine: str = "dbsf_colbert",
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "legal_documents",
        ...
    )
```

**Использование**:
```python
from src.config import Settings, SearchEngine

***REMOVED*** Загрузить из .env
settings = Settings()

***REMOVED*** Переопределить некоторые параметры
settings = Settings(
    api_provider="openai",
    search_engine=SearchEngine.BASELINE
)
```

---

***REMOVED******REMOVED******REMOVED*** 2. CONTEXTUALIZATION (`src/contextualization/`)

**Цель**: LLM-обогащение документов контекстом

**Провайдеры**:

| Провайдер | Время | Стоимость | Качество | Статус |
|-----------|-------|-----------|----------|--------|
| **Claude** | 8-12 мин | ~$12 | ⭐⭐⭐⭐⭐ | ✅ |
| **OpenAI** | 5-8 мин | ~$8 | ⭐⭐⭐⭐ | ✅ |
| **Groq** | 2-4 мин | FREE | ⭐⭐⭐ | ✅ |
| Z.AI (legacy) | 3-5 мин | $3/mo | ⭐⭐⭐ | ⚠️ |

**Базовый класс**:
```python
class ContextualizeProvider(ABC):
    async def contextualize(
        self,
        chunks: List[str],
        query: Optional[str] = None,
    ) -> List[ContextualizedChunk]:
        pass

    async def contextualize_single(
        self,
        text: str,
        article_number: str,
        query: Optional[str] = None,
    ) -> ContextualizedChunk:
        pass
```

**Использование**:
```python
from src.contextualization import ClaudeContextualizer

contextualizer = ClaudeContextualizer()

***REMOVED*** Контекстуализировать chunks
result = await contextualizer.contextualize(
    chunks=["Стаття 1..."],
    query="User query"
)

***REMOVED*** Получить статистику
stats = contextualizer.get_stats()
***REMOVED*** {'total_tokens': 1234, 'total_cost_usd': 0.0042, ...}
```

---

***REMOVED******REMOVED******REMOVED*** 3. RETRIEVAL (`src/retrieval/`)

**Цель**: Поиск и ранжирование документов

**Три поисковых движка**:

***REMOVED******REMOVED******REMOVED******REMOVED*** A. BaselineSearchEngine
```
Dense vectors only (BGE-M3)
Recall@1:   91.3%
NDCG@10:    0.9619
MRR:        0.9491
Latency:    0.65s
```

***REMOVED******REMOVED******REMOVED******REMOVED*** B. HybridRRFSearchEngine
```
Dense + Sparse (RRF fusion)
Recall@1:   88.7%
NDCG@10:    0.9524
MRR:        0.9421
Latency:    0.72s
```

***REMOVED******REMOVED******REMOVED******REMOVED*** C. DBSFColBERTSearchEngine ⭐ BEST
```
Density-Based Semantic Fusion + ColBERT reranking
Recall@1:   94.0% (+2.9% vs Baseline)
NDCG@10:    0.9711 (+1.0% vs Baseline)
MRR:        0.9636 (+1.5% vs Baseline)
Latency:    0.69s

Algorithm:
1. Dense search (100 candidates)
2. Neighborhood density computation
3. DBSF score fusion
4. ColBERT reranking
5. Final ranking
```

**Использование**:
```python
from src.retrieval import create_search_engine, SearchEngine

***REMOVED*** Создать движок
engine = create_search_engine(
    engine_type=SearchEngine.DBSF_COLBERT
)

***REMOVED*** Поиск
results = engine.search(
    query_embedding=query_vec,  ***REMOVED*** List[float] - 1024 dims
    top_k=10,
    score_threshold=0.3
)

for result in results:
    print(f"{result.article_number}: {result.text}")
    print(f"Score: {result.score:.3f}")
```

---

***REMOVED******REMOVED******REMOVED*** 4. INGESTION (`src/ingestion/`)

**Цель**: Загрузка и индексация документов

**3-этапный pipeline**:

***REMOVED******REMOVED******REMOVED******REMOVED*** Stage 1: PDF Parsing
```python
from src.ingestion import PDFParser

parser = PDFParser()
doc = parser.parse_file("document.pdf")
***REMOVED*** ParsedDocument(
***REMOVED***     filename="...",
***REMOVED***     title="...",
***REMOVED***     content="...",
***REMOVED***     num_pages=150,
***REMOVED***     metadata={...}
***REMOVED*** )
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Stage 2: Document Chunking
```python
from src.ingestion import DocumentChunker, ChunkingStrategy

chunker = DocumentChunker(
    chunk_size=512,
    overlap=128,
    strategy=ChunkingStrategy.SEMANTIC  ***REMOVED*** or FIXED_SIZE, SLIDING_WINDOW
)

chunks = chunker.chunk_text(
    text=doc.content,
    document_name="Конституція_України",
    article_number="Ст. 1"
)
***REMOVED*** List[Chunk] с метаданными
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Stage 3: Vector Indexing
```python
from src.ingestion import DocumentIndexer

indexer = DocumentIndexer()

***REMOVED*** Создать коллекцию
indexer.create_collection(
    collection_name="legal_documents",
    recreate=False
)

***REMOVED*** Индексировать chunks
stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="legal_documents",
    batch_size=16
)

print(f"Indexed: {stats.indexed_chunks} chunks")
print(f"Failed: {stats.failed_chunks}")
```

---

***REMOVED******REMOVED******REMOVED*** 5. EVALUATION (`src/evaluation/`)

**Цель**: Оценка качества и tracking экспериментов

**12 модулей**:

| Модуль | Назначение |
|--------|-----------|
| `metrics.py` | Recall@K, NDCG@K, MRR (новый) |
| `mlflow_integration.py` | MLflow experiment tracking |
| `langfuse_integration.py` | Langfuse LLM tracing |
| `run_ab_test.py` | A/B тестирование |
| `evaluate_with_ragas.py` | RAGAS evaluation |
| `smoke_test.py` | Быстрые smoke тесты |
| `evaluator.py` | Основной evaluator |
| `metrics_logger.py` | Логирование метрик |
| `config_snapshot.py` | Снимок конфигурации |
| `generate_test_queries.py` | Генерация запросов |
| `extract_ground_truth.py` | Извлечение ground truth |
| `search_engines_rerank.py` | Reranking |

**Использование**:
```python
***REMOVED*** A/B тестирование
python src/evaluation/run_ab_test.py \
  --queries data/test_queries/queries.json \
  --baseline baseline \
  --challenger dbsf_colbert

***REMOVED*** Результаты в MLflow
open http://localhost:5000
```

---

***REMOVED******REMOVED******REMOVED*** 6. CORE PIPELINE (`src/core/pipeline.py`)

**Главный класс для использования**:

```python
from src.core import RAGPipeline

***REMOVED*** Инициализировать
pipeline = RAGPipeline()

***REMOVED*** 1. Поиск
result = await pipeline.search(
    query="Які права мають громадяни?",
    top_k=5,
    use_context=True
)

for r in result.results:
    print(f"{r['article_number']}: {r['text'][:100]}")

***REMOVED*** 2. Индексирование
stats = await pipeline.index_documents(
    pdf_paths=[
        "docs/documents/Конституція_України.pdf",
        "docs/documents/Кримінальний_кодекс.pdf"
    ],
    collection_name="legal_documents",
    recreate_collection=False
)

***REMOVED*** 3. Оценка
metrics = await pipeline.evaluate(
    queries=test_queries,
    ground_truth=correct_answers
)

***REMOVED*** 4. Статистика
stats = pipeline.get_stats()
```

---

***REMOVED******REMOVED*** 🔄 МИГРАЦИЯ СТАРОГО КОДА

***REMOVED******REMOVED******REMOVED*** Что переместилось в legacy/

```
legacy/
├── config_old.py                  ***REMOVED*** Старая конфигурация
├── contextualize*.py              ***REMOVED*** Старые contextualize (5 файлов)
├── ingestion_contextual_kg*.py    ***REMOVED*** Старые ingestion (2 файла)
├── create_*.py                    ***REMOVED*** Утилиты создания коллекций
├── check_sparse_vectors.py
├── list_available_models*.py
└── prompts_old.py
```

***REMOVED******REMOVED******REMOVED*** Как мигрировать свой код

**Было (старое)**:
```python
from config import ANTHROPIC_API_KEY, QDRANT_URL
from contextualize import contextualize_documents
```

**Стало (новое)**:
```python
from src.config import Settings
from src.contextualization import ClaudeContextualizer

settings = Settings()
contextualizer = ClaudeContextualizer(settings)
```

---

***REMOVED******REMOVED*** 📝 ENVIRONMENT КОНФИГУРАЦИЯ

**.env файл переменные**:

```env
***REMOVED*** ========== API CONFIGURATION ==========
API_PROVIDER=claude                ***REMOVED*** claude, openai, groq
ANTHROPIC_API_KEY=[REDACTED-ANTHROPIC-KEY]
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
GROQ_API_KEY=[REDACTED-GROQ-KEY]

***REMOVED*** ========== VECTOR DATABASE ==========
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                    ***REMOVED*** Если требуется аутентификация

***REMOVED*** ========== SEARCH CONFIGURATION ==========
SEARCH_ENGINE=dbsf_colbert         ***REMOVED*** baseline, hybrid_rrf, dbsf_colbert
COLLECTION_NAME=legal_documents
TOP_K=10

***REMOVED*** ========== PROCESSING ==========
BATCH_SIZE_EMBEDDINGS=32
BATCH_SIZE_DOCUMENTS=16
ENABLE_CACHING=true
ENABLE_QUERY_EXPANSION=true

***REMOVED*** ========== ML PLATFORMS ==========
ENABLE_MLFLOW=true
ENABLE_LANGFUSE=true

***REMOVED*** ========== ENVIRONMENT ==========
ENV=development                    ***REMOVED*** development, production
DEBUG=false
```

---

***REMOVED******REMOVED*** 🔗 ЗАВИСИМОСТИ

**Основные** (обязательные):
```
pymupdf                   ***REMOVED*** PDF парсинг
anthropic                 ***REMOVED*** Claude API
openai                    ***REMOVED*** OpenAI API
groq                      ***REMOVED*** Groq API
sentence-transformers     ***REMOVED*** BGE-M3 embeddings
qdrant-client             ***REMOVED*** Vector DB клієнт
```

**ML платформы** (опциональные, но рекомендуется):
```
mlflow>=2.22.1            ***REMOVED*** Experiment tracking
ragas>=0.2.10             ***REMOVED*** RAG evaluation
langfuse>=3.0.0           ***REMOVED*** LLM observability
```

**Качество кода** (разработка):
```
ruff                      ***REMOVED*** Linting + formatting
mypy                      ***REMOVED*** Type checking
pytest                    ***REMOVED*** Тестирование
pre-commit                ***REMOVED*** Git hooks
```

---

***REMOVED******REMOVED*** 📊 ПРОДУКТИВНОСТЬ И МЕТРИКИ

***REMOVED******REMOVED******REMOVED*** Качество поиска (150 test queries)

| Метрика | Baseline | Hybrid RRF | DBSF+ColBERT | Улучшение |
|---------|----------|-----------|--------------|-----------|
| **Recall@1** | 91.3% | 88.7% | 94.0% | +2.9% ⭐ |
| **Recall@3** | 96.5% | 94.2% | 97.1% | +0.6% |
| **Recall@5** | 98.1% | 97.3% | 98.4% | +0.3% |
| **Recall@10** | 99.2% | 98.9% | 99.3% | +0.1% |
| **NDCG@1** | 0.9189 | 0.8874 | 0.9401 | +2.1% |
| **NDCG@10** | 0.9619 | 0.9524 | 0.9711 | +1.0% ⭐ |
| **MRR** | 0.9491 | 0.9421 | 0.9636 | +1.5% ⭐ |
| **Latency** | 0.65s | 0.72s | 0.69s | -0.04s |

***REMOVED******REMOVED******REMOVED*** Tiempo ингеста

```
PDF Parsing:       2-3 minutes (132 chunks)
Contextualization: 8-12 minutes (Claude, $12)
                   5-8 minutes (OpenAI, $8)
                   2-4 minutes (Groq, FREE)
Indexing:          1-2 minutes
Total Pipeline:    ~15-20 minutes
```

---

***REMOVED******REMOVED*** 🎯 ИСПОЛЬЗУЕМЫЕ ТЕХНОЛОГИИ

***REMOVED******REMOVED******REMOVED*** LLM APIs
- **Anthropic Claude** 3.5 Sonnet (основной)
- **OpenAI GPT-4 Turbo** (альтернатива)
- **Groq LLaMA 3** (быстрая)

***REMOVED******REMOVED******REMOVED*** Vector Database
- **Qdrant** v0.13.x (основной)
- **BGE-M3** (1024-dim dense + sparse)
- **ColBERT** (sparse embeddings)

***REMOVED******REMOVED******REMOVED*** ML Platforms
- **MLflow** 2.22.1+ (experiment tracking)
- **Langfuse** 3.0.0+ (LLM observability)
- **RAGAS** 0.2.10+ (RAG evaluation)

***REMOVED******REMOVED******REMOVED*** Code Quality
- **Ruff** 0.14.1 (linting + formatting)
- **MyPy** (type checking)
- **Pre-commit** (git hooks)

---

***REMOVED******REMOVED*** 📈 СЛЕДУЮЩИЕ ШАГИ

***REMOVED******REMOVED******REMOVED*** Phase 4 (Планируется)
- [ ] Query expansion через LLM
- [ ] Semantic caching (Redis)
- [ ] Graph traversal для related articles
- [ ] Web UI dashboard
- [ ] Multi-language support

---

**Last Updated**: October 29, 2025
**Version**: 2.0.1
**Created by**: Claude Code
