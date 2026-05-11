# Cache Degradation Behavior

Multi-tier semantic caching with graceful degradation when cache fails.

## Cache Tiers

### Tier 1: Embeddings Cache (RedisVL)
- **Purpose:** Skip re-encoding of repeated queries
- **Index:** `embeddings:v5`
- **TTL:** 7 days
- **Lookup:** Query text → cached embedding vector

### Tier 2: Semantic Result Cache (RedisVL)
- **Purpose:** Skip retrieval + generation for similar queries
- **Index:** `sem:v8:bge1024`
- **Threshold:** Varies by query type (see below)
- **TTL:** Per query type (configurable)

## Per-Query-Type Thresholds

| Query Type | Distance Threshold | Rationale |
|------------|-------------------|-----------|
| `FAQ` | 0.12 | High precision required |
| `ENTITY` | 0.10 | Entity/history-style specificity |
| `GENERAL` | 0.08 | Balanced |
| `STRUCTURED` | 0.05 | Most specific; strictest reuse |

**Note:** Semantic thresholds are RedisVL vector-distance cutoffs; lower values
are stricter. The separate store guard still uses `grade_confidence` on the RRF
scale.

`CHITCHAT` and `OFF_TOPIC` are not RAG cacheable query types. Apartment search
uses separate apartment tooling and should not be documented as a semantic
response-cache type unless the runtime policy changes.

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
Index: sem:v8:bge1024
Schema: query_text, query_type, language, response, sources, metadata
```

## Cache Scope

There is no explicit runtime bypass scope. RAG semantic-cache checks and stores
use `cache_scope="rag"`; history lookups use `cache_scope="history"`.
`CHITCHAT` and `OFF_TOPIC` skip the RAG path before semantic cache lookup.

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
| `telegram_bot/graph/nodes/cache.py` | Graph cache lookup/store nodes |
| `telegram_bot/pipelines/client.py` | Client direct cache lookup/store flow |
