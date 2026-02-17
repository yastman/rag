# Contextual RAG Pipeline - Overview

> **Быстрая справка для понимания всего flow системы**

**Версия:** 2.13.0
**Дата:** 2026-01-26
**Python:** 3.12+ (minimum 3.9)
**LLM:** zai-glm-4.7 (GLM-4, OpenAI-compatible API, streaming)

---

## Что это за система?

**Contextual RAG Pipeline** - production система для поиска по документам с:
- Гибридным поиском (RRF/DBSF + ColBERT rerank)
- Voyage AI embeddings (voyage-4-large/lite) + FastEmbed BM42
- Binary Quantization (40x ускорение, 75% экономия RAM)
- 6-уровневым кэшированием (Redis Stack)
- Query routing (CHITCHAT/SIMPLE/COMPLEX)
- ML платформой (MLflow, Langfuse, RAGAS)
- Telegram bot интерфейсом со streaming

**Use cases:**
- Уголовный кодекс Украины (1,294 документа, BGE-M3)
- Болгарская недвижимость (92 документа, Voyage-4)

---

## Архитектура High-Level

```
┌─────────────────┐
│  Input Source   │  ← PDF, CSV, DOCX
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Ingestion     │  ← UniversalDocumentParser + DocumentChunker (1024 chars)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Embeddings    │  ← VoyageService (voyage-4-large) или BGE-M3
│                 │     + FastEmbed BM42 (sparse)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Qdrant DB     │  ← Binary Quantization, Named vectors
│                 │     (dense + sparse + colbert)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Query Processing│  ← QueryPreprocessor (translit, RRF weights)
│                 │     QueryRouter (CHITCHAT/SIMPLE/COMPLEX)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Retrieval     │  ← HybridRRFColBERT (default) или DBSF
│                 │     4 search engine варианта
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   6-Tier Cache  │  ← Semantic, Embeddings, Analyzer, Search, Rerank, Conv
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Contextualization│ ← LLM streaming (GLM-4/Claude/GPT)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Response     │  ← Telegram bot / API
└─────────────────┘
```

---

## Data Flow: От источника до ответа

### Step 1: Ingestion (Загрузка документов)

**Модуль:** `src/ingestion/`

**Компоненты:**

| Класс | Назначение |
|-------|-----------|
| `UniversalDocumentParser` | PDF/DOCX/CSV парсинг через PyMuPDF/Docling |
| `DocumentChunker` | Hybrid chunking (1024 chars, overlap) |
| `VoyageIndexer` | Индексация через Voyage AI |
| `DocumentIndexer` | Индексация через BGE-M3 (legacy) |

**Схема данных:**

```python
ContextualDocument(
    topic="Недвижимость в Болгарии",
    context="Обзор рынка...",
    chunks=[
        ContextualChunk(text="...", metadata={...}),
        ...
    ]
)
```

---

### Step 2: Embeddings (Векторизация)

**Два варианта:**

#### Voyage AI (рекомендуется)

```python
from telegram_bot.services import VoyageService

service = VoyageService(
    model_docs="voyage-4-large",     # 1024-dim, для документов
    model_queries="voyage-4-lite",   # Для запросов (asymmetric)
    model_rerank="rerank-2.5",       # 32K context window
)

# Embeddings
doc_vecs = await service.embed_documents(["doc1", "doc2"])
query_vec = await service.embed_query("поисковый запрос")

# Reranking
results = await service.rerank("query", documents, top_k=5)
```

**Matryoshka dimensions:** 2048, 1024, 512, 256 (настраиваемо)

#### BGE-M3 (локально, high RAM)

```python
from src.models import get_bge_m3_model

model = get_bge_m3_model()  # Singleton, экономит 4-6GB RAM
output = model.encode(
    texts,
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True
)
# Returns: dense (1024-dim) + sparse (BM42) + ColBERT multi-vectors
```

---

### Step 3: Indexing (Сохранение в Qdrant)

**Коллекции:**

| Collection | Documents | Embeddings | Quantization |
|-----------|-----------|------------|--------------|
| `contextual_bulgaria_voyage4` | 92 | Voyage-4 | Binary |
| `legal_documents` | 1,294 | BGE-M3 | Scalar Int8 |

**Структура Point:**

```python
PointStruct(
    id=uuid.uuid4(),
    vector={
        "dense": [1024 floats],        # Semantic search
        "bm42": SparseVector(...),     # Keyword search
        "colbert": [[N×1024] floats],  # Reranking (optional)
    },
    payload={
        "page_content": chunk.text,
        "metadata": {
            "document_name": "...",
            "article_number": "...",
            ...
        }
    }
)
```

**Binary Quantization (v2.13.0):**

```python
from telegram_bot.services import QdrantService

qdrant = QdrantService(
    use_quantization=True,           # 40x faster
    quantization_rescore=True,       # Maintain accuracy
    quantization_oversampling=2.0,   # Fetch 2x, rescore top_k
)

# A/B testing: disable per-request
results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    quantization_ignore=True,  # Skip quantization
)
```

---

### Step 4: Query Processing

**Модуль:** `telegram_bot/services/`

#### QueryPreprocessor (Translit + RRF Weights)

```python
from telegram_bot.services import QueryPreprocessor

pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5")
# Returns:
# {
#   "normalized_query": "apartments in Солнечный берег корпус 5",
#   "rrf_weights": {"dense": 0.2, "sparse": 0.8},  # Exact → sparse
#   "cache_threshold": 0.05,
#   "is_exact": True
# }
```

| Тип запроса | RRF weights | Cache threshold |
|-------------|-------------|-----------------|
| Semantic (без IDs) | 0.6/0.4 (dense) | 0.10 |
| Exact (IDs, корпус) | 0.2/0.8 (sparse) | 0.05 |

#### QueryRouter (RAG Skipping)

```python
from telegram_bot.services import classify_query, QueryType, get_chitchat_response

query_type = classify_query("Привет!")  # QueryType.CHITCHAT
if query_type == QueryType.CHITCHAT:
    response = get_chitchat_response(query)  # Skip RAG entirely

# QueryType.SIMPLE  → Light RAG, skip rerank
# QueryType.COMPLEX → Full RAG + rerank
```

---

### Step 5: Retrieval (Поиск)

**Модуль:** `src/retrieval/search_engines.py`

**4 варианта:**

| Engine | Pipeline | Recall@1 | Latency |
|--------|----------|----------|---------|
| **HybridRRFColBERT** (default) | Dense + Sparse → RRF → ColBERT | 0.94 | ~1.0s |
| DBSFColBERT | Dense + Sparse → DBSF → ColBERT | 0.93 | ~0.93s |
| HybridRRF | Dense + Sparse → RRF | 0.91 | ~0.7s |
| Baseline | Dense only | 0.91 | ~0.5s |

**SDK Pattern (v2.13.0):**

```python
from qdrant_client import models

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

---

### Step 6: Cache (6-Tier)

**Модуль:** `telegram_bot/services/cache.py`

| Уровень | TTL | Назначение |
|---------|-----|-----------|
| Semantic | 2h | Похожие запросы (cosine 0.15) |
| Embeddings | 7d | Voyage/BGE-M3 vectors |
| Analyzer | 24h | LLM filter extraction |
| Search | 2h | Qdrant results |
| Rerank | 2h | Voyage rerank results |
| Conversation | Session | Message history |

```python
from telegram_bot.services import CacheService

cache = CacheService()
# Auto-caches: embeddings, search results, rerank, analyzer
```

---

### Step 7: LLM Contextualization

**Модуль:** `src/contextualization/`

**Провайдеры:**

| Provider | Model | Use case |
|----------|-------|----------|
| Z.AI | GLM-4 (zai-glm-4.7) | Default, streaming |
| Anthropic | Claude 3.5 Sonnet | High quality |
| OpenAI | GPT-4 Turbo | Fallback |
| Groq | Mixtral | Fast, cheap |

**Streaming response:**

```python
from telegram_bot.services import LLMService

llm = LLMService()
async for chunk in llm.stream_response(query, context):
    yield chunk  # Real-time streaming to Telegram
```

---

## Supervisor Architecture (#240)

**Feature flag:** `USE_SUPERVISOR=true` (default: off)

Replaces monolithic `classify_node` routing with LLM-based supervisor that selects tools:

```
User Query → Supervisor LLM (gpt-4o-mini) → tool_choice
  → rag_search      → build_graph().ainvoke() (existing 10-node RAG pipeline)
  → history_search  → HistoryService.search_user_history() (Qdrant + BGE-M3)
  → direct_response → pass-through (greetings, chitchat)
```

**Observability:** Single Langfuse trace with scores:
- `agent_used` (CATEGORICAL) — which tool was selected
- `supervisor_latency_ms` (NUMERIC) — routing decision time
- `supervisor_model` (CATEGORICAL) — model used for routing

**Runtime context:** Tools receive `user_id`/`session_id` via `RunnableConfig.configurable`.

---

## Telegram Bot Services

**Модуль:** `telegram_bot/services/`

| Service | Purpose |
|---------|---------|
| `VoyageService` | Unified embeddings + reranking |
| `QdrantService` | Smart Gateway: RRF, quantization, MMR |
| `CacheService` | 6-tier multi-level cache |
| `QueryPreprocessor` | Translit, RRF weights |
| `QueryRouter` | CHITCHAT/SIMPLE/COMPLEX classification |
| `QueryAnalyzer` | LLM-based filter extraction |
| `RetrieverService` | Dense vector search |
| `CESCPersonalizer` | Lazy personalization |
| `UserContextService` | User preferences extraction |
| `LLMService` | Streaming LLM responses |

---

## External Services

| Service | Port | Purpose |
|---------|------|---------|
| Qdrant | 6333 | Vector database |
| Redis Stack | 6379, 8001 | Semantic cache (RediSearch) |
| MLflow | 5000 | Experiment tracking |
| Langfuse | 3001 | LLM tracing |

---

## Структура проекта

```
rag-fresh/
├── src/                          # Core RAG pipeline
│   ├── ingestion/                # Document parsing, chunking, indexing
│   ├── retrieval/                # 4 search engine variants
│   ├── contextualization/        # LLM providers (Claude, OpenAI, Groq)
│   ├── cache/                    # RedisSemanticCache
│   ├── config/                   # Settings, enums
│   ├── evaluation/               # RAGAS, MLflow, Langfuse
│   ├── models/                   # BGE-M3 singleton
│   └── core/                     # RAGPipeline orchestrator
│
├── telegram_bot/                 # Bot + 13 unified services
│   ├── agents/                   # Multi-agent supervisor (#240)
│   │   ├── supervisor.py         # build_supervisor_graph (LLM + ToolNode)
│   │   ├── rag_agent.py          # RAG graph wrapper tool
│   │   ├── history_agent.py      # HistoryService wrapper tool
│   │   └── tools.py              # Tool factories with runtime context
│   ├── services/                 # VoyageService, QdrantService, etc.
│   └── bot.py                    # Main handler
│
├── scripts/                      # Utilities
│   ├── test_quantization_ab.py   # Binary quantization A/B testing
│   └── index_contextual.py       # Document indexing
│
├── tests/                        # pytest (unit, integration, e2e, smoke, load)
├── docs/                         # Documentation
├── AGENTS.md                     # Codex workflow + instruction chain root
└── pyproject.toml                # Dependencies, Ruff, MyPy
```

---

## Конфигурация

### Environment Variables (.env)

```bash
# Required
VOYAGE_API_KEY=...
OPENAI_API_KEY=...
QDRANT_API_KEY=...
TELEGRAM_BOT_TOKEN=...

# Optional
ANTHROPIC_API_KEY=...
LANGFUSE_PUBLIC_KEY=...
MLFLOW_TRACKING_URI=...

# Voyage models (defaults)
VOYAGE_MODEL_DOCS=voyage-4-large
VOYAGE_MODEL_QUERIES=voyage-4-lite
VOYAGE_RERANK_MODEL=rerank-2.5

# Qdrant quantization (defaults)
QDRANT_USE_QUANTIZATION=true
QDRANT_QUANTIZATION_RESCORE=true
QDRANT_QUANTIZATION_OVERSAMPLING=2.0
```

---

## Performance (2026 Defaults)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `search_top_k` | 20 | Fewer candidates → faster Qdrant |
| `use_quantization` | true | 40x faster, 75% less RAM |
| `rerank_top_k` | 3 | Fewer chunks in LLM context |
| `max_tokens` | 1024 | Faster generation |
| Rerank cache TTL | 2h | Skip API calls |
| Semantic threshold | 0.15 | 85% similarity |

**Search latency:** ~1.0s (HybridRRFColBERT)
**Recall@1:** 0.94

---

## Quick Commands

```bash
# Install
make install-dev

# Start services
docker compose -f docker-compose.dev.yml up -d

# Run tests
make test
make test-cov

# Code quality
make check    # lint + types
make fix      # auto-fix

# Deploy
make deploy-code
```

---

## См. также

- `AGENTS.md` - корневые инструкции Codex
- `docs/agent-rules/workflow.md` - цикл разработки и команды
- `docs/QDRANT_STACK.md` - конфигурация Qdrant
- `docs/LOCAL-DEVELOPMENT.md` - локальная разработка
- `CACHING.md` - 6-tier cache architecture

---

**Last Updated:** 2026-01-26
**Version:** 2.13.0
