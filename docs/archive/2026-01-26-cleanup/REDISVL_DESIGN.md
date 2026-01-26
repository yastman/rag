# Adaptive Graph-Vector RAG 2026 - Design Plan

**Project:** Bulgarian Property Search Bot
**Date:** 2026-01-21
**Status:** Draft

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ADAPTIVE GRAPH-VECTOR RAG 2026                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │   HyDE      │───▶│  LightRAG   │───▶│   CESC      │             │
│  │  Rewriter   │    │ Graph+Vector│    │Personalize  │             │
│  └─────────────┘    └─────────────┘    └─────────────┘             │
│         │                  │                  │                     │
│         ▼                  ▼                  ▼                     │
│  ┌─────────────────────────────────────────────────────┐           │
│  │              HYBRID RETRIEVAL ENGINE                 │           │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐ │           │
│  │  │ BGE-M3  │  │  BM42   │  │  RRF    │  │ColBERT │ │           │
│  │  │ Dense   │  │ Sparse  │  │ Fusion  │  │Rerank  │ │           │
│  │  │1024-dim │  │  SPLADE │  │         │  │        │ │           │
│  │  └─────────┘  └─────────┘  └─────────┘  └────────┘ │           │
│  └─────────────────────────────────────────────────────┘           │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────┐           │
│  │              MULTI-TIER CACHING (RedisVL)           │           │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │           │
│  │  │ Semantic │  │Embeddings│  │  User    │          │           │
│  │  │  Cache   │  │  Cache   │  │ Context  │          │           │
│  │  │langcache │  │  BGE-M3  │  │  CESC    │          │           │
│  │  └──────────┘  └──────────┘  └──────────┘          │           │
│  └─────────────────────────────────────────────────────┘           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

### 2.1 Feature Matrix

| Technology | Purpose | Version | Coolness |
|------------|---------|---------|----------|
| **RedisVL** | Semantic caching + vector ops | 0.11+ | 🔥🔥🔥 |
| **LightRAG** | Knowledge Graph + Vector hybrid | latest | 🔥🔥🔥 |
| **CESC** | Context-Enabled Semantic Cache | Redis 2025 | 🔥🔥🔥 |
| **HyDE** | Hypothetical Document Embeddings | custom | 🔥🔥 |
| **BM42** | SPLADE-like sparse vectors | Qdrant 2025 | 🔥🔥 |
| **Matryoshka** | Adaptive dimension retrieval | BGE-M3 | 🔥🔥 |
| **ColBERT** | Late interaction reranking | existing | 🔥🔥 |
| **Cerebras GLM-4.7** | Main LLM generation | API | 🔥 |

### 2.2 Embedding Models

| Model | Dimensions | Use Case |
|-------|------------|----------|
| BGE-M3 (dense) | 1024 | Qdrant semantic search |
| BGE-M3 (sparse) | variable | BM42-style keyword matching |
| BGE-M3 (ColBERT) | 1024 × N | Late interaction reranking |
| langcache-embed-v1 | 256 | Redis SemanticCache matching |

---

## 3. Components Detail

### 3.1 RedisVL SemanticCache

**Problem:** Current cache broken (`num_docs: 0`) due to `decode_responses=True` corrupting binary vectors.

**Solution:** Use native RedisVL with `langcache-embed-v1` vectorizer.

```python
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.utils.vectorize import HFTextVectorizer

vectorizer = HFTextVectorizer(model="redis/langcache-embed-v1")
semantic_cache = SemanticCache(
    name="rag_llm_cache",
    redis_url="redis://localhost:6379",
    ttl=48 * 3600,  # 48 hours
    distance_threshold=0.15,  # cosine distance (~85% similarity)
    vectorizer=vectorizer,
)

# Usage - vectorizer handles embeddings internally
await semantic_cache.acheck(prompt=query)
await semantic_cache.astore(prompt=query, response=answer)
```

### 3.2 CESC (Context-Enabled Semantic Cache)

**Concept:** On cache HIT, personalize response using user context + lightweight LLM.

```
Traditional Cache:  Query → Exact Match → Generic Response
Semantic Cache:     Query → Meaning Match → Generic Response
CESC:               Query → Meaning Match → Personalized Response
```

**User Context Schema:**

```python
user_context = {
    "user_id": 12345,
    "preferences": {
        "cities": ["Солнечный берег", "Несебр"],
        "budget_min": 50000,
        "budget_max": 100000,
        "property_types": ["apartment", "studio"],
        "distance_to_sea_max": 500,
        "rooms_min": 1,
        "rooms_max": 3,
    },
    "history_summary": "Ищет 2-комнатные квартиры у моря в бюджете до 100к",
    "last_queries": [
        "квартиры в Солнечном береге",
        "студии до 60000 евро",
    ],
    "interaction_count": 15,
    "language": "ru",
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-01-21T14:30:00Z",
}
```

**CESC Flow:**

```python
class CESCPersonalizer:
    async def get_response(self, query: str, user_id: int) -> str:
        # 1. Check semantic cache
        cached = await self.semantic_cache.acheck(prompt=query)

        if cached:
            # 2. Get user context
            ctx = await self.cache.get_user_context(user_id)

            # 3. Personalize with lightweight LLM (gpt-4o-mini)
            return await self.personalize(
                cached_response=cached[0]["response"],
                user_context=ctx,
                query=query,
            )

        # 4. Full RAG pipeline on cache miss
        return await self.full_rag_pipeline(query, user_id)

    async def personalize(self, cached_response: str, user_context: dict, query: str) -> str:
        prompt = f"""
        Адаптируй ответ под пользователя:

        Кешированный ответ: {cached_response}

        Контекст пользователя:
        - Предпочитаемые города: {user_context['preferences'].get('cities', [])}
        - Бюджет: {user_context['preferences'].get('budget_min')}-{user_context['preferences'].get('budget_max')}€
        - История: {user_context.get('history_summary', 'новый пользователь')}

        Сохрани все факты, но персонализируй подачу информации.
        Ответ должен быть на русском языке.
        """
        return await self.mini_llm.generate(prompt)  # gpt-4o-mini / Cerebras
```

### 3.3 LightRAG Knowledge Graph

**Concept:** Combine vector retrieval with knowledge graph traversal for better context.

**Entity Types:**
- `City` (Город)
- `District` (Район)
- `Complex` (Жилой комплекс)
- `Developer` (Застройщик)
- `Property` (Объект недвижимости)
- `Amenity` (Удобство: море, парк, магазин)

**Relation Types:**
- `LOCATED_IN` (Property → District → City)
- `BUILT_BY` (Complex → Developer)
- `NEAR_TO` (Property → Amenity)
- `PART_OF` (Property → Complex)
- `HAS_AMENITY` (Complex → Amenity)

```python
from lightrag import LightRAG, QueryParam

rag = LightRAG(
    working_dir="./lightrag_data",
    llm_model_func=cerebras_complete,
    embedding_func=bge_m3_embed,
)

# Index documents (extracts entities & relations automatically)
await rag.ainsert(documents)

# Query with hybrid mode (vector + graph)
result = await rag.aquery(
    "Квартиры в Солнечном береге от застройщика Тера близко к морю",
    param=QueryParam(
        mode="hybrid",  # "naive" | "local" | "global" | "hybrid"
        top_k=10,
    )
)
```

### 3.4 HyDE (Hypothetical Document Embeddings)

**Concept:** Generate hypothetical answer first, then use its embedding for retrieval (better than query embedding).

```python
class HyDEQueryExpander:
    """Hypothetical Document Embeddings for better retrieval."""

    async def expand(self, query: str) -> tuple[str, list[float]]:
        # 1. Generate hypothetical ideal answer
        hypothetical = await self.llm.generate(
            prompt=f"""
            Ты эксперт по недвижимости в Болгарии.
            Напиши идеальный развёрнутый ответ на вопрос пользователя.
            Включи конкретные детали: цены, районы, характеристики.

            Вопрос: {query}

            Идеальный ответ:
            """,
            max_tokens=300,
        )

        # 2. Embed the hypothetical (better semantic match than raw query)
        embedding = await self.embedder.embed(hypothetical)

        return hypothetical, embedding
```

### 3.5 Qdrant Hybrid Search (BM42 + Dense + ColBERT)

**Collection Schema:**

```python
from qdrant_client.models import (
    VectorParams, SparseVectorParams,
    Distance, Modifier
)

# Create collection with multiple vector types
await qdrant.create_collection(
    collection_name="apartments_v2",
    vectors_config={
        "dense": VectorParams(
            size=1024,
            distance=Distance.COSINE,
        ),
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(
            modifier=Modifier.IDF,  # BM42-style IDF weighting
        ),
    },
)
```

**Indexing:**

```python
from qdrant_client.models import PointStruct, SparseVector

# Generate all embeddings
dense_vec = await bge_m3.embed_dense(text)
sparse_vec = await bge_m3.embed_sparse(text)  # or BM42

await qdrant.upsert(
    collection_name="apartments_v2",
    points=[
        PointStruct(
            id=uuid4(),
            vector={
                "dense": dense_vec,
            },
            sparse_vectors={
                "sparse": SparseVector(
                    indices=sparse_vec.indices,
                    values=sparse_vec.values,
                ),
            },
            payload={
                "title": "2-комнатная квартира в Солнечном береге",
                "price": 75000,
                "city": "Солнечный берег",
                "rooms": 2,
                "area": 65,
                "distance_to_sea": 300,
                "text": text,
            },
        )
    ]
)
```

**Hybrid Search with RRF:**

```python
from qdrant_client.models import Prefetch, FusionQuery

results = await qdrant.query_points(
    collection_name="apartments_v2",
    prefetch=[
        # Dense retrieval
        Prefetch(
            query=dense_query_vec,
            using="dense",
            limit=100,
        ),
        # Sparse retrieval (keyword matching)
        Prefetch(
            query=SparseVector(
                indices=sparse_query.indices,
                values=sparse_query.values,
            ),
            using="sparse",
            limit=100,
        ),
    ],
    query=FusionQuery(fusion="rrf"),  # Reciprocal Rank Fusion
    limit=10,
    with_payload=True,
)
```

---

## 4. Implementation Phases

### Phase 1: RedisVL SemanticCache Fix (Day 1-2)

**Files:**
- `telegram_bot/services/cache.py`
- `telegram_bot/bot.py`

**Tasks:**
- [ ] Add `HFTextVectorizer` import
- [ ] Initialize SemanticCache with `langcache-embed-v1`
- [ ] Change `acheck(vector=)` → `acheck(prompt=)`
- [ ] Change `astore(prompt, response, vector=)` → `astore(prompt, response)`
- [ ] Test cache hit/miss

### Phase 2: User Context Storage (Day 2-3)

**Files:**
- `telegram_bot/services/cache.py`
- `telegram_bot/services/user_context.py` (new)

**Tasks:**
- [ ] Create `UserContextService` class
- [ ] Implement Redis Hash storage for user context
- [ ] Auto-extract preferences from queries
- [ ] Update context on each interaction

### Phase 3: CESC Personalization (Day 3-4)

**Files:**
- `telegram_bot/services/cesc.py` (new)
- `telegram_bot/bot.py`

**Tasks:**
- [ ] Create `CESCPersonalizer` class
- [ ] Integrate with SemanticCache
- [ ] Add personalization prompt template
- [ ] Configure lightweight LLM (gpt-4o-mini)

### Phase 4: LightRAG Integration (Day 5-6)

**Files:**
- `src/retrieval/lightrag_engine.py` (new)
- `scripts/build_knowledge_graph.py` (new)

**Tasks:**
- [ ] Install LightRAG: `pip install lightrag-hku`
- [ ] Define entity/relation extraction prompts
- [ ] Build knowledge graph from existing documents
- [ ] Implement hybrid retrieval (vector + graph)

### Phase 5: HyDE Query Expansion (Day 6-7)

**Files:**
- `telegram_bot/services/hyde.py` (new)

**Tasks:**
- [ ] Create `HyDEQueryExpander` class
- [ ] Integrate with RAG pipeline
- [ ] A/B test HyDE vs direct query

### Phase 6: Qdrant BM42 Hybrid (Day 7-8)

**Files:**
- `src/retrieval/search_engines.py`
- `scripts/reindex_with_sparse.py` (new)

**Tasks:**
- [ ] Add sparse vector generation (BM42/BGE-M3 sparse)
- [ ] Update collection schema
- [ ] Reindex all documents
- [ ] Implement RRF fusion search

### Phase 7: Testing & Validation (Day 9-10)

**Tasks:**
- [ ] Unit tests for each component
- [ ] Integration tests for full pipeline
- [ ] Performance benchmarks
- [ ] Cache hit rate monitoring

---

## 5. Configuration

### Environment Variables

```bash
# Redis
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your_password

# Cache TTLs (seconds)
SEMANTIC_CACHE_TTL=172800       # 48 hours
EMBEDDINGS_CACHE_TTL=604800     # 7 days
USER_CONTEXT_TTL=2592000        # 30 days

# SemanticCache
SEMANTIC_CACHE_DISTANCE_THRESHOLD=0.15

# CESC
CESC_ENABLED=true
CESC_PERSONALIZATION_MODEL=gpt-4o-mini
CESC_MAX_CONTEXT_LENGTH=500

# LightRAG
LIGHTRAG_WORKING_DIR=./lightrag_data
LIGHTRAG_MODE=hybrid

# HyDE
HYDE_ENABLED=true
HYDE_MAX_TOKENS=300
```

### Docker Compose

```yaml
version: '3.8'

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

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}

  bge-m3:
    image: ghcr.io/huggingface/text-embeddings-inference:latest
    ports:
      - "8001:80"
    volumes:
      - models_cache:/data
    command: --model-id BAAI/bge-m3

volumes:
  redis_data:
  qdrant_data:
  models_cache:
```

---

## 6. Expected Performance

| Metric | Without Cache | Cache HIT | CESC HIT |
|--------|--------------|-----------|----------|
| Latency | 2-3s | <100ms | ~200ms |
| LLM Tokens | 500-1000 | 0 | ~100 |
| Cost/query | $0.02 | $0 | $0.002 |
| Personalization | None | None | Full |

**Target Metrics:**
- Cache hit rate: >40% after 200 queries
- P95 latency (cache hit): <200ms
- P95 latency (cache miss): <3s
- User satisfaction: improved relevance

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| langcache-embed-v1 download fails | Cache broken | Fallback to no-cache mode |
| CESC degrades answer quality | Bad UX | A/B testing, quality monitoring |
| LightRAG entity extraction errors | Wrong graph | Human review, confidence thresholds |
| Redis memory overflow | Service crash | maxmemory + LRU eviction |
| HyDE adds latency | Slow response | Async generation, caching |

---

## 8. Success Criteria

- [ ] SemanticCache indexes documents (`num_docs > 0`)
- [ ] Cache hit rate > 40% after warmup
- [ ] CESC personalization improves user engagement
- [ ] LightRAG provides better context for complex queries
- [ ] All existing tests pass
- [ ] Documentation updated
- [ ] No regression in search quality (Recall@10 >= 94%)

---

## 9. References

- [RedisVL Documentation](https://docs.redisvl.com/)
- [Redis CESC Blog](https://redis.io/blog/building-a-context-enabled-semantic-cache-with-redis/)
- [LightRAG Paper](https://arxiv.org/abs/2410.05779)
- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [BGE-M3 Model](https://huggingface.co/BAAI/bge-m3)
- [langcache-embed-v1](https://huggingface.co/redis/langcache-embed-v1)
- [Qdrant Hybrid Search](https://qdrant.tech/documentation/concepts/hybrid-queries/)
- [HyDE Paper](https://arxiv.org/abs/2212.10496)
