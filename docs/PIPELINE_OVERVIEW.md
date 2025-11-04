# Contextual RAG Pipeline - Полный Overview

> **Быстрая справка для понимания всего flow системы**

**Версия:** 2.3.0
**Дата:** 2025-11-04
**Цель:** Быстро понять как работает вся система, чтобы не повторять действия

---

## 🎯 Что это за система?

**Contextual RAG Pipeline** - production система для поиска по документам с:
- Гибридным поиском (RRF + ColBERT)
- ML платформой (MLflow, Langfuse)
- Redis кэшем
- Security (PII redaction, budget guards)

**Основной use case:** Поиск по Уголовному кодексу Украины
**Новый use case:** Любые документы + CSV данные (недвижимость, каталоги и т.д.)

---

## 📊 Архитектура High-Level

```
┌─────────────────┐
│  Input Source   │  ← PDF, CSV, DOCX, URLs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Ingestion     │  ← Docling + Chunker
│   (парсинг)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Embeddings    │  ← BGE-M3 (dense + sparse + ColBERT)
│   (векторизация)│     1024-dim vectors
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Qdrant DB     │  ← Vector database
│   (хранение)    │     Collections + metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Retrieval     │  ← Hybrid RRF + ColBERT rerank
│   (поиск)       │     Variant A (default) / Variant B
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Contextualization│ ← LLM processing (Claude/GPT)
│   (обработка)   │     + Redis cache
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Response     │  ← Final answer
└─────────────────┘
```

---

## 🔄 Data Flow: От источника до ответа

### Step 1: Ingestion (Загрузка документов)

**Модуль:** `src/ingestion/`

**Поддерживаемые форматы:**
- PDF → `pdf_parser.py` (через Docling)
- CSV → `csv_to_qdrant.py` (новый, через Docling)
- DOCX, HTML → (через Docling)

**Компоненты:**

1. **Docling Document Converter**
   - Парсит любые форматы в единый формат
   - Извлекает структуру, таблицы, изображения
   - Конвертирует в Docling Document

2. **Chunker** (`chunker.py`)
   - Режет документ на chunks
   - Стратегии:
     - `FIXED_SIZE` - фиксированный размер (512 chars, 128 overlap)
     - `SEMANTIC` - по семантическим границам (параграфы, секции)
     - `SLIDING_WINDOW` - скользящее окно

3. **Metadata Extraction**
   - Извлекает метаданные: article_number, chapter, section
   - Для CSV: все поля как metadata

**Пример для CSV:**

```python
# src/ingestion/csv_to_qdrant.py
indexer = CSVToQdrantIndexer()
records = indexer.read_csv("demo_BG.csv")
# Каждая строка CSV → текст + metadata
# "Недвижимость: Квартира... Город: Солнечный берег..."
```

**Output:** Список `Chunk` объектов с text + metadata

---

### Step 2: Embeddings (Векторизация)

**Модуль:** `src/ingestion/indexer.py`

**Модель:** `BAAI/bge-m3`
- Dense vectors: 1024-dim (основной семантический поиск)
- Sparse vectors: bag-of-words (для точных совпадений)
- ColBERT: multi-vector для reranking

**Процесс:**

```python
# В indexer.py
embedding_model = SentenceTransformer("BAAI/bge-m3")
embeddings = embedding_model.encode(
    texts,
    batch_size=32,
    normalize_embeddings=True
)
```

**Батчинг:**
- Batch size: 32 (configurable)
- Нормализация для cosine similarity

**Output:** Vectors [1024-dim float] для каждого chunk

---

### Step 3: Indexing (Сохранение в Qdrant)

**Модуль:** `src/ingestion/indexer.py`

**Qdrant Collections:**

1. **`legal_documents`** (основная)
   - 1294 точек
   - Векторы: `dense` (1024) + `colbert` (1024 multi-vector)
   - Metadata: article_number, chapter, section, text

2. **`bulgarian_properties`** (новая, пример CSV)
   - 4 точки (demo_BG.csv)
   - Векторы: `dense` (1024)
   - Metadata: все поля CSV (Город, Цена, Комнат, etc.)

**Структура Point:**

```python
PointStruct(
    id=uuid.uuid4(),
    vector=embedding,  # [1024-dim]
    payload={
        "text": chunk.text,
        "document_name": "...",
        "article_number": "...",  # для legal docs
        # + все остальные поля
    }
)
```

**Индексы для fast filtering:**
- `article_number` (keyword)
- `document_name` (keyword)

---

### Step 4: Retrieval (Поиск)

**Модуль:** `src/retrieval/`

**Два варианта (Variant A - default, Variant B - experimental):**

#### **Variant A: Hybrid RRF + ColBERT**

`src/retrieval/hybrid_rrf_colbert_search_engine.py`

**3-stage pipeline:**

1. **Prefetch** (100 docs)
   - Dense search (top 100)
   - Sparse search (top 100)

2. **RRF Fusion** (Reciprocal Rank Fusion)
   ```
   score = Σ 1/(k + rank_i)
   k = 60 (константа)
   ```
   - Объединяет результаты dense + sparse
   - Top 20 после fusion

3. **ColBERT Rerank** (server-side)
   - Multi-vector reranking на Qdrant
   - Max-sim scoring
   - Final top 10

**Performance:**
- Recall@1: ~94%
- NDCG@10: ~0.97
- Latency: ~1.0s

#### **Variant B: Hybrid DBSF + ColBERT**

`src/retrieval/dbsf_colbert_search_engine.py`

**Отличие:** DBSF вместо RRF
- DBSF (Distribution-Based Score Fusion)
- Statistical normalization
- 7% faster (0.937s)
- Top result agreement: 66.7% с Variant A

**Когда использовать:**
- Variant A: production default
- Variant B: experimentation, faster processing

**Config:**

```python
# src/config/constants.py
DEFAULT_SEARCH_ENGINE = SearchEngine.HYBRID_RRF_COLBERT
# или
DEFAULT_SEARCH_ENGINE = SearchEngine.DBSF_COLBERT
```

---

### Step 5: Cache (Redis)

**Модуль:** `src/cache/`

**2-уровневый кэш:**

1. **Embedding Cache** (Level 1)
   - TTL: 30 дней
   - Ключ: hash(query text)
   - Значение: embedding vector
   - Экономия: GPU compute

2. **Response Cache** (Level 2)
   - TTL: 5-60 минут (зависит от типа запроса)
   - Ключ: hash(query + search_params)
   - Значение: полный response
   - Экономия: LLM calls (90% cost savings)

**Versioning:**
- Schema version: `v1`
- Автоматическая инвалидация при изменении

**Пример:**

```python
from src.cache import RedisSemanticCache

cache = RedisSemanticCache()
# Проверка кэша
cached = cache.get(query="как наказывается кража?")
if cached:
    return cached

# ... выполнить поиск + LLM ...

# Сохранить в кэш
cache.set(query="...", response="...", ttl=3600)
```

---

### Step 6: LLM Processing (Contextualization)

**Модуль:** `src/contextualization/`

**Провайдеры:**
- Anthropic (Claude) - default
- OpenAI (GPT)
- Groq

**Процесс:**

1. Получить топ chunks из retrieval
2. Построить промпт с контекстом
3. Отправить в LLM
4. PII redaction (если нужно)
5. Budget guards (проверка лимитов)

**Security:**

```python
# src/security/
- pii_redaction.py: Ukrainian patterns (phone, email, passport)
- budget_guards.py: $10/day, $300/month limits
```

---

### Step 7: Observability (Мониторинг)

**Модуль:** `src/observability/`

**Стек:**
- OpenTelemetry → traces
- Tempo → trace storage
- Prometheus → metrics
- Grafana → dashboards

**Traced operations:**
- Document parsing
- Embedding generation
- Vector search
- LLM calls
- Cache hits/misses

**Langfuse:**
- LLM tracing
- Cost tracking
- Quality metrics

---

## 🗂️ Структура проекта (детально)

```
contextual_rag/
│
├── src/
│   ├── ingestion/           ← Загрузка и парсинг
│   │   ├── pdf_parser.py    ← PDF через Docling
│   │   ├── csv_to_qdrant.py ← CSV через Docling (NEW)
│   │   ├── chunker.py       ← Стратегии чанкинга
│   │   └── indexer.py       ← Индексация в Qdrant
│   │
│   ├── retrieval/           ← Поиск
│   │   ├── hybrid_rrf_colbert_search_engine.py  ← Variant A (default)
│   │   ├── dbsf_colbert_search_engine.py        ← Variant B
│   │   └── base_search_engine.py                ← Base interface
│   │
│   ├── cache/               ← Redis кэш
│   │   ├── redis_semantic_cache.py  ← 2-level cache
│   │   └── README.md
│   │
│   ├── contextualization/   ← LLM обработка
│   │   ├── llm_client.py    ← Anthropic/OpenAI/Groq
│   │   └── prompts.py       ← Промпт темплейты
│   │
│   ├── evaluation/          ← ML платформа
│   │   ├── mlflow_tracker.py    ← Эксперименты
│   │   ├── langfuse_tracer.py   ← LLM tracing
│   │   └── ragas_evaluator.py   ← Quality metrics
│   │
│   ├── governance/          ← Model Registry
│   │   └── model_registry.py    ← Staging → Production
│   │
│   ├── security/            ← Безопасность
│   │   ├── pii_redaction.py     ← PII фильтрация
│   │   └── budget_guards.py     ← Лимиты
│   │
│   ├── observability/       ← Мониторинг
│   │   └── tracing.py           ← OpenTelemetry
│   │
│   ├── config/              ← Конфигурация
│   │   ├── settings.py          ← Settings class
│   │   └── constants.py         ← Defaults
│   │
│   └── core/                ← Main pipeline
│       └── rag_pipeline.py      ← Orchestration
│
├── scripts/                 ← Утилиты
│   ├── qdrant_backup.sh     ← Backup Qdrant
│   └── qdrant_restore.sh    ← Restore
│
├── tests/
│   ├── data/golden_test_set.json  ← 150 test queries
│   └── test_*.py
│
├── docs/
│   ├── PIPELINE_OVERVIEW.md       ← ВОТ ЭТОТ ДОКУМЕНТ
│   ├── ML_PLATFORM_INTEGRATION_PLAN.md
│   └── architecture/
│
├── .env                     ← Секреты (НЕ в Git!)
├── pyproject.toml           ← Зависимости
└── README.md                ← Главный README
```

---

## 🚀 Как запустить каждый компонент

### 1. Добавить PDF документы

```bash
python src/ingestion/pdf_parser.py --input data/document.pdf
python src/ingestion/indexer.py --collection legal_documents
```

### 2. Добавить CSV данные

```bash
python src/ingestion/csv_to_qdrant.py \
    --input demo_BG.csv \
    --collection bulgarian_properties \
    --recreate
```

### 3. Поисковый запрос (Variant A)

```python
from src.retrieval import HybridRRFColBERTSearchEngine

engine = HybridRRFColBERTSearchEngine()
results = engine.search(
    query="квартира в Несебре",
    collection_name="bulgarian_properties",
    limit=5
)
```

### 4. Полный RAG pipeline

```python
from src.core import RAGPipeline

pipeline = RAGPipeline()
response = pipeline.query(
    question="какая средняя цена квартиры в Солнечном берегу?",
    collection="bulgarian_properties"
)
```

### 5. Мониторинг

```bash
# Prometheus metrics
curl http://localhost:9090/metrics

# Grafana dashboards
open http://localhost:3000

# MLflow experiments
open http://localhost:5000

# Langfuse traces
open http://localhost:3001
```

---

## 🔧 Конфигурация

### Environment Variables (.env)

```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=3e7321df905ee908...

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=...

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=http://localhost:3001
```

### Settings (Python)

```python
from src.config import Settings

settings = Settings(
    # Search
    search_engine=SearchEngine.HYBRID_RRF_COLBERT,  # или DBSF_COLBERT
    top_k=10,
    score_threshold=0.7,

    # LLM
    api_provider=APIProvider.ANTHROPIC,
    model_name="claude-3-5-sonnet-20241022",
    temperature=0.0,

    # Processing
    batch_size_embeddings=32,
    batch_size_documents=10,
)
```

---

## 📈 Метрики и Performance

### Качество (RAGAS)

- **Faithfulness:** ≥ 0.85 (точность ответов)
- **Precision:** ≥ 0.80 (релевантность chunks)
- **Recall:** ≥ 0.90 (полнота покрытия)

### Скорость

| Operation | Latency |
|-----------|---------|
| Embedding generation | 50-100ms (batch 32) |
| Vector search (Variant A) | ~1.0s |
| Vector search (Variant B) | ~0.94s |
| LLM call (Claude) | 2-5s |
| Redis cache hit | <10ms |

### Экономия

- **Cache hit rate:** 70-80%
- **Cost savings:** 90% (через cache)
- **Token usage:** Tracked in Langfuse

---

## 🐛 Troubleshooting

### Проблема: "Must provide API key" (Qdrant)

```python
# Решение: Добавить API key
client = QdrantClient(
    url="http://localhost:6333",
    api_key=os.getenv("QDRANT_API_KEY")
)
```

### Проблема: Redis connection error

```bash
# Проверить контейнер
docker ps | grep redis

# Проверить пароль
echo $REDIS_PASSWORD
```

### Проблема: Slow search

```python
# Использовать Variant B (быстрее на 7%)
settings = Settings(
    search_engine=SearchEngine.DBSF_COLBERT
)
```

---

## 🎓 Обучающие материалы

### Для понимания компонентов:

1. **Docling:** Парсинг документов
   - https://github.com/docling-project/docling
   - Supports: PDF, DOCX, CSV, HTML

2. **BGE-M3:** Embeddings
   - https://huggingface.co/BAAI/bge-m3
   - Dense + Sparse + ColBERT

3. **Qdrant:** Vector DB
   - https://qdrant.tech/documentation/
   - Hybrid search, multivector

4. **RRF vs DBSF:**
   - RRF: Reciprocal Rank Fusion (default)
   - DBSF: Distribution-Based Score Fusion (faster)

---

## 📝 Quick Reference

**Добавить новый тип документа:**

1. Создать parser в `src/ingestion/`
2. Использовать `DocumentChunker` для chunks
3. Индексировать через `DocumentIndexer`
4. Profit!

**Поменять search engine:**

```python
# В src/config/constants.py
DEFAULT_SEARCH_ENGINE = SearchEngine.DBSF_COLBERT  # вместо HYBRID_RRF_COLBERT
```

**Добавить новую коллекцию:**

```python
indexer = DocumentIndexer()
indexer.create_collection("new_collection")
```

**Очистить Redis кэш:**

```bash
docker exec ai-redis-secure redis-cli -a $REDIS_PASSWORD FLUSHDB
```

---

## ✅ Checklist: Что нужно знать

- [x] Ingestion flow: Document → Chunks → Embeddings → Qdrant
- [x] Retrieval: Variant A (RRF) vs Variant B (DBSF)
- [x] Cache: 2-level (embeddings + responses)
- [x] Security: PII + budget guards
- [x] Monitoring: OpenTelemetry + Langfuse + MLflow
- [x] CSV support: `csv_to_qdrant.py`
- [x] Collections: `legal_documents` (1294 points), `bulgarian_properties` (4 points)

---

**Этот документ должен дать полное понимание системы за 10-15 минут чтения.**
**При добавлении новых компонентов - обновить этот файл!**

**Last Updated:** 2025-11-04
**Maintainer:** yastman
