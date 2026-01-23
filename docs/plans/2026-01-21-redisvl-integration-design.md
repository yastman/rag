# RedisVL Integration Design Plan

**Date:** 2026-01-21
**Status:** Draft
**Author:** Claude

## 1. Executive Summary

Интеграция RedisVL 0.11+ в Telegram бот для недвижимости Болгарии. Гибридная архитектура: Qdrant для поиска + Redis для кеширования с CESC (Context-Enabled Semantic Caching).

## 2. Current State Analysis

### 2.1 Существующая архитектура

```
User Query → BGE-M3 Embedding → Qdrant Search → LLM Generation → Response
                 ↓                    ↓              ↓
            [broken cache]      [no cache]     [no cache]
```

**Проблемы:**
- SemanticCache не индексирует документы (`num_docs: 0`)
- Причина: `decode_responses=True` ломает бинарные векторы
- Embeddings cache работает (JSON сериализация)
- Нет персонализации ответов

### 2.2 Текущие компоненты

| Компонент | Статус | Технология |
|-----------|--------|------------|
| Vector Search | ✅ Working | Qdrant + BGE-M3 (1024-dim) |
| Semantic Cache | ❌ Broken | RedisVL (неправильная конфигурация) |
| Embeddings Cache | ✅ Working | Redis JSON |
| Query Analyzer Cache | ✅ Working | Redis JSON |
| Search Results Cache | ✅ Working | Redis JSON |
| Conversation Memory | ✅ Working | Redis LIST |

## 3. Target Architecture

### 3.1 Гибридная модель (Qdrant + Redis)

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER QUERY                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SEMANTIC CACHE CHECK                           │
│         (RedisVL + langcache-embed-v1, 256-dim)                 │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ User Context │───▶│ Cache Lookup │───▶│ CESC Refine  │       │
│  │   (Redis)    │    │  (RedisVL)   │    │ (GPT-4o-mini)│       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
         │                                        │
         │ MISS                                   │ HIT (personalized)
         ▼                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAG PIPELINE                                  │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  BGE-M3      │───▶│   Qdrant     │───▶│  Cerebras    │       │
│  │ (1024-dim)   │    │ Hybrid Search│    │  GLM-4.7     │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  Features:                                                       │
│  - Dense vectors (BGE-M3)                                        │
│  - Sparse vectors (BM42) [future]                               │
│  - RRF fusion                                                    │
│  - ColBERT rerank                                               │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CACHE STORE                                    │
│  - Store in SemanticCache (langcache-embed-v1)                  │
│  - Update User Context                                          │
│  - Update Conversation Memory                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Разделение моделей эмбеддингов

| Задача | Модель | Размерность | Причина |
|--------|--------|-------------|---------|
| Qdrant Search | BGE-M3 | 1024 | Высокая точность, мультиязычность |
| Semantic Cache | langcache-embed-v1 | 256 | Оптимизирован для cache matching, быстрый |

**Почему два разных embeddings:**
1. **BGE-M3** - лучшее качество для semantic search, но тяжелый (4-6GB RAM)
2. **langcache-embed-v1** - специально обучен Redis для cache similarity, легкий (~100MB)

## 4. RedisVL Features to Implement

### 4.1 SemanticCache (Priority: Critical)

```python
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.utils.vectorize import HFTextVectorizer

# Инициализация с правильным vectorizer
vectorizer = HFTextVectorizer(model="redis/langcache-embed-v1")
semantic_cache = SemanticCache(
    name="rag_llm_cache",
    redis_url="redis://localhost:6379",
    ttl=48 * 3600,  # 48 hours
    distance_threshold=0.15,  # cosine distance (0.15 ≈ 85% similarity)
    vectorizer=vectorizer,
)

# Использование
await semantic_cache.acheck(prompt=query)  # NOT vector=
await semantic_cache.astore(prompt=query, response=answer)  # NOT vector=
```

### 4.2 EmbeddingsCache (Priority: High)

Текущая реализация через Redis JSON работает. Опционально можно мигрировать на RedisVL:

```python
from redisvl.extensions.cache.embeddings import EmbeddingsCache

embed_cache = EmbeddingsCache(
    name="bge_m3_cache",
    redis_url="redis://localhost:6379",
    ttl=7 * 24 * 3600,  # 7 days
)

# Интеграция с vectorizer
vectorizer = HFTextVectorizer(
    model="BAAI/bge-m3",
    cache=embed_cache,
)
```

**Решение:** Оставить текущую JSON-based реализацию - она проще и работает с remote BGE-M3 service.

### 4.3 CESC - Context-Enabled Semantic Cache (Priority: Medium)

**Концепция:** При cache HIT - персонализировать ответ через легкую LLM.

```python
# User Context Structure (Redis Hash)
user_context = {
    "user_id": "12345",
    "preferences": {
        "preferred_cities": ["Солнечный берег", "Несебр"],
        "budget_range": "50000-100000",
        "property_type": "apartment"
    },
    "history_summary": "Интересуется 2-комнатными квартирами у моря",
    "last_results_count": 5,
    "language": "ru"
}

# CESC Flow
if cached_response := await semantic_cache.acheck(prompt=query):
    # 1. Get user context
    context = await get_user_context(user_id)

    # 2. Personalize with lightweight LLM
    personalized = await personalize_response(
        cached_response=cached_response,
        user_context=context,
        model="gpt-4o-mini"  # or Cerebras for speed
    )
    return personalized
```

### 4.4 Multi-Vector Queries (Priority: Low, Future)

RedisVL 0.11+ поддерживает multi-vector search:

```python
# Пример: поиск по тексту + изображению
results = await index.query(
    vectors={
        "text_embedding": text_vec,
        "image_embedding": image_vec,
    },
    weights={"text_embedding": 0.7, "image_embedding": 0.3}
)
```

## 5. Implementation Plan

### Phase 1: Fix SemanticCache (Day 1)

**Files to modify:**
- `telegram_bot/services/cache.py`
- `telegram_bot/bot.py`

**Changes:**

1. Add HFTextVectorizer import
2. Initialize SemanticCache with langcache-embed-v1
3. Change `acheck(vector=...)` → `acheck(prompt=...)`
4. Change `astore(prompt, response, vector=...)` → `astore(prompt, response)`

### Phase 2: Add User Context Storage (Day 2)

**New methods in CacheService:**

```python
async def store_user_context(self, user_id: int, context: dict):
    """Store user context in Redis Hash."""
    key = f"user_context:{user_id}"
    await self.redis_client.hset(key, mapping={
        k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        for k, v in context.items()
    })
    await self.redis_client.expire(key, 30 * 24 * 3600)  # 30 days

async def get_user_context(self, user_id: int) -> dict:
    """Get user context from Redis Hash."""
    key = f"user_context:{user_id}"
    data = await self.redis_client.hgetall(key)
    return {k: json.loads(v) if v.startswith('{') else v for k, v in data.items()}

async def update_user_preferences(self, user_id: int, query: str, results: list):
    """Auto-update user preferences based on queries and results."""
    # Extract cities, price ranges, property types from query/results
    # Update user context incrementally
```

### Phase 3: Implement CESC Personalization (Day 3)

**New service: CESCPersonalizer**

```python
class CESCPersonalizer:
    """Context-Enabled Semantic Cache personalizer."""

    async def personalize(
        self,
        cached_response: str,
        user_context: dict,
        query: str,
    ) -> str:
        """Personalize cached response using user context."""

        prompt = f"""
        Cached answer: {cached_response}

        User context:
        - Preferred cities: {user_context.get('preferred_cities', [])}
        - Budget: {user_context.get('budget_range', 'any')}
        - History: {user_context.get('history_summary', 'new user')}

        Current query: {query}

        Adapt the cached answer to be more relevant to this user.
        Keep the factual content but personalize the presentation.
        """

        return await self.llm.generate(prompt, model="gpt-4o-mini")
```

### Phase 4: Testing & Validation (Day 4)

1. Unit tests for SemanticCache
2. Integration tests for CESC flow
3. Performance benchmarks (latency, hit rate)
4. A/B testing cached vs non-cached responses

## 6. Configuration

### 6.1 Environment Variables

```bash
# Redis
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your_password

# Cache TTLs (seconds)
SEMANTIC_CACHE_TTL=172800      # 48 hours
EMBEDDINGS_CACHE_TTL=604800    # 7 days
ANALYZER_CACHE_TTL=86400       # 24 hours
SEARCH_CACHE_TTL=7200          # 2 hours

# SemanticCache
SEMANTIC_CACHE_DISTANCE_THRESHOLD=0.15  # cosine distance

# CESC
CESC_ENABLED=true
CESC_PERSONALIZATION_MODEL=gpt-4o-mini
```

### 6.2 Docker Compose Update

```yaml
services:
  redis-stack:
    image: redis/redis-stack:latest
    ports:
      - "6379:6379"
      - "8001:8001"  # RedisInsight
    volumes:
      - redis_data:/data
    environment:
      - REDIS_ARGS=--requirepass ${REDIS_PASSWORD}
```

## 7. Metrics & Monitoring

### 7.1 Cache Metrics

```python
metrics = {
    "semantic": {
        "hits": 0,
        "misses": 0,
        "hit_rate": 0.0,
        "avg_latency_ms": 0,
        "personalization_count": 0,
    },
    "embeddings": {...},
    "analyzer": {...},
    "search": {...},
}
```

### 7.2 Expected Performance

| Metric | Without Cache | With Cache | With CESC |
|--------|--------------|------------|-----------|
| Latency | 2-3s | <100ms | ~150ms |
| LLM Tokens | 500-1000 | 0 | ~50 (mini) |
| Cost per query | $0.01-0.02 | $0 | $0.001 |

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| langcache-embed-v1 model download fails | Cache won't work | Fallback to no-cache mode |
| CESC personalization degrades quality | User experience | A/B test, quality monitoring |
| Redis memory overflow | Service crash | Set maxmemory + eviction policy |
| Cache stale data | Incorrect answers | TTL + manual invalidation API |

## 9. Future Enhancements

### 9.1 LightRAG Integration (Knowledge Graph)

```python
# После индексации документов - построить граф знаний
from lightrag import LightRAG

rag = LightRAG(
    working_dir="./lightrag_cache",
    llm_model_func=cerebras_llm,
    embedding_func=bge_m3_embed,
)

# Dual retrieval: vector + graph
results = await rag.aquery(
    query,
    param=QueryParam(mode="hybrid")  # vector + knowledge graph
)
```

### 9.2 Matryoshka Embeddings

```python
# Truncatable embeddings для адаптивного поиска
# BGE-M3 поддерживает: 1024 → 512 → 256 → 128 → 64

# Быстрый первичный поиск (64-dim)
candidates = await qdrant.search(vector[:64], limit=100)

# Точный rerank (1024-dim)
final = rerank_with_full_vectors(candidates, vector)
```

### 9.3 BM42 Sparse Vectors

```python
***REMOVED*** 2025: нативные sparse vectors
await qdrant.upsert(
    collection_name="apartments",
    points=[
        PointStruct(
            id=1,
            vector={
                "dense": bge_m3_dense,
                "sparse": bm42_sparse,  # NEW
            },
            payload={...}
        )
    ]
)
```

## 10. Acceptance Criteria

- [ ] SemanticCache индексирует документы (num_docs > 0)
- [ ] Cache hit rate > 30% после 100 запросов
- [ ] Latency при cache hit < 150ms
- [ ] CESC персонализация работает корректно
- [ ] Все существующие тесты проходят
- [ ] Документация обновлена

## 11. References

- [RedisVL Documentation](https://docs.redisvl.com/)
- [Redis CESC Blog](https://redis.io/blog/building-a-context-enabled-semantic-cache-with-redis/)
- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [BGE-M3 Model](https://huggingface.co/BAAI/bge-m3)
- [langcache-embed-v1](https://huggingface.co/redis/langcache-embed-v1)
