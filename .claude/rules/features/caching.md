---
paths: "**/cache*.py, src/cache/**, **/integrations/cache.py"
---

# Caching System

6-tier caching for RAG pipeline: semantic + 5 exact caches + conversation history.

## Architecture

CacheLayerManager is the sole cache implementation (CacheService legacy removed).

```
LangGraph Pipeline:
  classify → cache_check_node → [HIT] → respond
                              → [MISS] → retrieve_node → grade → rerank → generate → cache_store_node
```

## Key Files

| File | Description |
|------|-------------|
| `telegram_bot/integrations/cache.py` | CacheLayerManager (~300 LOC) |
| `telegram_bot/graph/nodes/cache.py` | cache_check_node + cache_store_node |
| `telegram_bot/graph/nodes/retrieve.py` | retrieve_node (hybrid RRF + search/sparse cache) |

## Cache Tiers (CacheLayerManager)

| Tier | Cache Type | TTL | Key Pattern |
|------|------------|-----|-------------|
| 1 | Semantic (LLM responses) | per query_type | `sem:v5:bge1024` |
| 2 | Embeddings (dense) | 7d | `embeddings:v5:{hash}` |
| 3 | Sparse embeddings | 7d | `sparse:v5:{hash}` |
| 4 | Analysis results | 24h | `analysis:v5:{hash}` |
| 5 | Search results | 2h | `search:v5:{hash}` |
| 6 | Rerank results | 2h | `rerank:v5:{hash}` |
| + | Conversation history | 2h | `conversation:{user_id}` (LIST, 20 msgs) |

## Semantic Cache Thresholds (per query_type)

| Query Type | Threshold | TTL | Notes |
|------------|-----------|-----|-------|
| STRUCTURED | 0.05 | 2h | Strictest — IDs, numbers |
| GENERAL | 0.08 | 1h | Default |
| ENTITY | 0.10 | 1h | Named entities |
| FAQ | 0.12 | 24h | Most lenient, long TTL |

## CacheLayerManager Usage

```python
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://redis:6379")
await cache.initialize()

# Semantic cache (query-type threshold)
cached = await cache.check_semantic(query, vector=embedding, query_type="FAQ")
await cache.store_semantic(query, response, vector=embedding, query_type="FAQ")

# Exact caches (generic)
await cache.store_exact("search", hash_key, results)
result = await cache.get_exact("search", hash_key)

# Convenience methods
embedding = await cache.get_embedding("query text")
await cache.store_embedding("query text", [0.1, ...])

# Conversation (single message, uses Redis pipeline: 1 round-trip)
await cache.store_conversation(user_id=123, role="user", content="hello")
# Batch conversation (multiple messages in 1 pipeline round-trip)
await cache.store_conversation_batch(user_id=123, messages=[("user", "hi"), ("assistant", "hello")])
history = await cache.get_conversation(user_id=123, last_n=5)
await cache.clear_conversation(user_id=123)

# Cache clearing (bot /clearcache command)
await cache.clear_semantic_cache()           # Semantic cache (redisvl aclear or SCAN fallback)
await cache.clear_by_tier("embeddings")      # Exact tier (embeddings/sparse/analysis/search/rerank)
await cache.clear_all_caches()               # All tiers → dict[tier, deleted_count]

# Metrics
stats = cache.get_metrics()  # per-tier hits/misses/hit_rate
```

## Redis Pipelines

Both `store_conversation` and `store_conversation_batch` use async Redis pipelines:

```python
async with self.redis.pipeline(transaction=False) as pipe:
    for role, content in messages:
        pipe.rpush(key, json.dumps({"role": role, "content": content}))
    pipe.ltrim(key, -max_messages, -1)
    pipe.expire(key, ttl)
    await pipe.execute()  # Single round-trip for all operations
```

## Graph Nodes

### cache_check_node

Computes embedding (cached or fresh), checks semantic cache. Uses capability-based detection (`callable + iscoroutinefunction` on `aembed_hybrid`) for hybrid path:

1. Check embedding cache → if miss:
   - **BGEM3HybridEmbeddings**: `aembed_hybrid()` → dense + sparse in 1 call, cache both
   - **Other**: `aembed_query()` → dense only
   - On error → sets `embedding_error=True`, `route_cache` → respond
2. Check semantic cache with dense vector (only for `CACHEABLE_QUERY_TYPES`: FAQ, ENTITY, STRUCTURED, GENERAL)
3. Returns `embeddings_cache_hit` flag for Langfuse scoring

```python
result = await cache_check_node(state, cache=cache, embeddings=embeddings)
# Returns: {cache_hit, cached_response, query_embedding, embeddings_cache_hit, embedding_error, latency_stages}
```

### cache_store_node

Stores response + conversation after LLM generation (uses `store_conversation_batch`):

```python
result = await cache_store_node(state, cache=cache)
# Stores semantic cache + conversation history (batch pipeline, 1 round-trip)
```

### retrieve_node

Hybrid RRF search with multi-level caching:

```python
result = await retrieve_node(state, cache=cache, sparse_embeddings=sparse, qdrant=qdrant)
# Flow: search cache → sparse cache → qdrant.hybrid_search_rrf() → cache results
```

## Key Details

**Query normalization for cache keys:** `_normalize_query_for_cache()` lowercases, strips trailing punctuation — `"ВНЖ?"` and `"внж"` hash to the same key, avoiding duplicate API calls.

**SemanticCache filterable fields:** `query_type`, `language`, `user_id`, `cache_scope`, `agent_role` (tag fields in RedisVL index `sem:v5:bge1024`).

## Dependencies

- Container: `dev-redis` (6379)
- Library: `redisvl` (lazy-loaded to avoid 7.5s import)
- `CACHE_VERSION = "v5"` in `integrations/cache.py`
- Vectorizer: `BgeM3CacheVectorizer` for semantic cache vectors

## Testing

```bash
pytest tests/unit/integrations/test_cache_layers.py -v   # 23 tests
pytest tests/unit/graph/test_cache_nodes.py -v            # 7 tests
pytest tests/unit/graph/test_retrieve_node.py -v          # 5 tests
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Redis connection refused` | `docker compose up -d redis` |
| Cache pollution after model change | Bump `CACHE_VERSION` |
| False positive hits | Lower threshold in `cache_thresholds` |
| High miss rate | Raise threshold or increase TTL |
| Semantic cache timeout | Check Redis latency, adjust `cache_timeout` (default 0.3s) |
