# Cache Degradation Behavior

Multi-tier semantic caching with graceful degradation when cache fails.

## Cache Tiers

### Tier 1: Embeddings Cache (RedisVL)
- **Purpose:** Skip re-encoding of repeated queries
- **Key:** `embeddings:v5` index
- **TTL:** 7 days
- **Lookup:** Query text → cached embedding vector

### Tier 2: Semantic Result Cache (RedisVL)
- **Purpose:** Skip retrieval + generation for similar queries
- **Key:** `sem:v5:bge1024` index
- **Threshold:** Varies by query type (see below)
- **TTL:** Per query type (configurable)

## Per-Query-Type Thresholds

| Query Type | Distance Threshold | Rationale |
|------------|-------------------|-----------|
| `FAQ` | 0.12 | High precision required |
| `GENERAL` | 0.08 | Balanced |
| `APARTMENT` | 0.10 | Price/location specificity |
| `CHITCHAT` | 0.15 | Lenient matching |
| `OFF_TOPIC` | 1.0 | Bypass cache entirely |

**Note:** Thresholds are on RRF scale (~0.005–0.15), NOT cosine similarity [0-1].

## Degradation Modes

### Mode 1: Cache Unavailable (Redis Down)
- Embeddings cache miss → re-encode
- Semantic cache miss → proceed without caching
- **User impact:** Slower response, no cache benefits
- **Monitoring:** `cache_errors` metric

### Mode 2: Embedding Service Down
- Cannot compute embedding → bypass cache lookup
- Proceed to full retrieval pipeline
- **User impact:** Full latency, no cache hit possible

### Mode 3: Qdrant Unavailable
- Cache hit → attempt to use cached response
- Cache miss → fail with error
- **User impact:** Degraded quality if cache miss

## Cache Key Structure

```
# Embeddings cache
Index: embeddings:v5
Schema: text (str), embedding (dense[1024])

# Semantic result cache
Index: sem:v5:bge1024
Schema: query_text, query_type, language, response, sources, metadata
```

## Forcing Cache Bypass

Set `cache_scope=disabled` in request to bypass all caching:

```python
# In graph state
state["cache_scope"] = "disabled"
```

## Monitoring

| Metric | Description |
|--------|-------------|
| `cache_hit_total` | Total cache hits by type |
| `cache_miss_total` | Total cache misses by type |
| `cache_error_total` | Cache errors by tier |
| `cache_latency_ms` | Cache operation latency |

## Configuration

Environment variables:
- `REDIS_PASSWORD` — Redis auth (required)
- `CACHE_TTL_DEFAULT` — Default TTL in seconds
- `CACHE_EMBEDDING_TTL` — Embeddings cache TTL (default: 604800 = 7 days)

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/integrations/cache.py` | CacheLayerManager |
| `telegram_bot/services/cache_policy.py` | Cacheability decisions |
| `telegram_bot/graph/nodes/cache_check.py` | Cache lookup node |
| `telegram_bot/graph/nodes/cache_store.py` | Cache write node |
