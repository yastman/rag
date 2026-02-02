---
paths: "**/cache*.py, src/cache/**"
---

***REMOVED*** Caching System

6-tier caching system for RAG pipeline optimization.

***REMOVED******REMOVED*** Purpose

Reduce API calls, latency, and costs by caching at multiple levels:
- Semantic cache for LLM responses
- Embeddings cache for query vectors
- Search results cache
- Rerank results cache
- QueryAnalyzer results cache
- Sparse embeddings cache

***REMOVED******REMOVED*** Architecture

```
Query → SemanticCache check → [HIT: return cached]
                           → [MISS: Embeddings → Search → Rerank → LLM → cache result]
```

***REMOVED******REMOVED*** Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/cache.py` | 33 | CacheService main class |
| `telegram_bot/services/cache.py` | 30 | CACHE_SCHEMA_VERSION |
| `src/cache/redis_semantic_cache.py` | - | Legacy implementation |

***REMOVED******REMOVED*** Cache Tiers

| Tier | Cache Type | TTL | Key Pattern |
|------|------------|-----|-------------|
| 1 | Semantic (LLM responses) | 48h | `sem:v2:{vectorizer_id}` |
| 1 | Embeddings (query vectors) | 7d | `emb:v2:{hash}` |
| 1 | Conversation history | ∞ | `rag_conversations:v2:{vectorizer_id}` |
| 2 | QueryAnalyzer results | 24h | `analysis:v2:{hash}` |
| 2 | Search results | 2h | `search:v2:{index_ver}:{hash}` |
| 2 | Rerank results | 2h | `rerank:v2:{hash}` |
| 2 | Sparse embeddings | 7d | `sparse:v2:{model}:{hash}` |

***REMOVED******REMOVED*** Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `semantic_cache_ttl` | 48h | LLM response cache lifetime |
| `embeddings_cache_ttl` | 7d | Query embedding cache lifetime |
| `distance_threshold` | 0.20 | Cosine distance for semantic match (lower = stricter) |
| `CACHE_SCHEMA_VERSION` | "v2" | Bump when changing models |

***REMOVED******REMOVED*** Distance Thresholds

| Query Type | Threshold | Similarity |
|------------|-----------|------------|
| Exact (IDs, corpus) | 0.05 | 95% required |
| Semantic (general) | 0.10 | 90% required |

***REMOVED******REMOVED*** How It Works

1. **Initialize:** `CacheService(redis_url)` connects to Redis
2. **Check semantic cache:** Query embedding → Redis vector search
3. **On HIT:** Return cached response (optionally personalize via CESC)
4. **On MISS:** Full RAG pipeline → store result with TTL

***REMOVED******REMOVED*** Common Patterns

***REMOVED******REMOVED******REMOVED*** Check semantic cache

```python
from telegram_bot.services.cache import CacheService

cache = CacheService(redis_url="redis://localhost:6379")
await cache.initialize(vectorizer)  ***REMOVED*** Pass embedding function

***REMOVED*** Check cache
cached = await cache.check_semantic_cache(query, threshold=0.10)
if cached:
    return cached["response"]
```

***REMOVED******REMOVED******REMOVED*** Store in cache

```python
await cache.store_semantic_cache(
    query=query,
    response=llm_response,
    metadata={"query_type": "semantic"}
)
```

***REMOVED******REMOVED******REMOVED*** Version bumping

When changing embedding models:

```python
***REMOVED*** telegram_bot/services/cache.py:30
CACHE_SCHEMA_VERSION = "v3"  ***REMOVED*** Was "v2"
```

Old keys expire naturally via TTL.

***REMOVED******REMOVED******REMOVED*** Conversation history (SemanticMessageHistory)

Index name includes version AND vectorizer to prevent schema mismatch:

```python
***REMOVED*** Index format: rag_conversations:{version}:{vectorizer_id}
***REMOVED*** Examples:
***REMOVED***   rag_conversations:v2:userbase768  (USE_LOCAL_EMBEDDINGS=true)
***REMOVED***   rag_conversations:v2:voyage1024   (Voyage API)
```

**Why vectorizer_id?** Different vectorizers have different dimensions (768 vs 1024). Mixing them causes schema mismatch.

**Cleanup old indices:**
```bash
docker exec dev-redis redis-cli FT.DROPINDEX rag_conversations DD
docker exec dev-redis redis-cli FT.DROPINDEX "rag_conversations:v2" DD
```

***REMOVED******REMOVED*** Dependencies

- Container: `dev-redis` (6379)
- Library: `redisvl` (lazy-loaded to avoid 7.5s import)

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/test_cache.py -v
pytest tests/unit/test_semantic_cache.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| `Redis connection refused` | `docker compose -f docker-compose.dev.yml up -d redis` |
| Cache pollution after model change | Bump `CACHE_SCHEMA_VERSION` |
| False positive hits | Lower `distance_threshold` |
| High miss rate | Raise `distance_threshold` or increase TTL |
| `schema does not match` for conversation history | Old index exists; drop with `FT.DROPINDEX ... DD` |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new cache tier

1. Add TTL parameter to `CacheService.__init__`
2. Add key pattern constant (e.g., `NEW_CACHE_PREFIX = "new:v2:"`)
3. Implement `check_new_cache()` and `store_new_cache()` methods
4. Add metrics tracking in `self.metrics["new"]`
5. Write tests in `tests/unit/test_cache.py`

***REMOVED******REMOVED******REMOVED*** Monitoring cache effectiveness

```python
***REMOVED*** Get hit/miss stats
stats = cache.get_metrics()
***REMOVED*** {"semantic": {"hits": 42, "misses": 18}, ...}
```
