# Cache Degradation Behavior

> **Related docs:**
> - [Troubleshooting: Semantic Cache](TROUBLESHOOTING_CACHE.md) -- debugging guide for cache misses, key inspection, and monitoring
> - [Runbook: Redis Cache Degradation](runbooks/REDIS_CACHE_DEGRADATION.md) -- incident response for Redis service failures

Multi-tier semantic caching with graceful degradation when cache fails.
This document describes the **design and architecture** of the cache system.

## Cache Tiers

`CacheLayerManager` in [`telegram_bot/integrations/cache.py`](../telegram_bot/integrations/cache.py) implements 5 cache tiers:

| # | Tier | Backend | Index / Key Prefix | TTL | Purpose |
|---|------|---------|-------------------|-----|---------|
| 1 | Semantic | RedisVL `SemanticCache` | `sem:v8:bge1024` | Per query type (see below) | LLM response caching by vector similarity |
| 2 | Embeddings | RedisVL `EmbeddingsCache` | `embeddings:v5` | 7 days | Dense embedding vector cache |
| 3 | Sparse | Redis exact (SET/GET) | `sparse:v5:<hash>` | 7 days | Sparse embedding cache |
| 4 | Search | Redis exact (SET/GET) | `search:v5:<hash>` | 2 hours | Search results cache |
| 5 | Rerank | Redis exact (SET/GET) | `rerank:v5:<hash>` | 2 hours | Reranked results cache |

Additionally, **Conversation history** is stored in Redis LISTs (`conversation:<user_id>`, 20 messages, 2h TTL) but is not managed as a cache tier.

### Version Constants

```python
CACHE_VERSION = "v5"            # Exact-cache key prefix version
SEMANTIC_CACHE_VERSION = "v8"   # Semantic cache index version
```

When models or schemas change, bump these constants to invalidate stale entries.

## Per-Query-Type Thresholds

Semantic cache uses per-type distance thresholds (cosine distance; lower = stricter):

| Query Type | Distance Threshold | TTL |
|------------|-------------------|-----|
| `FAQ` | 0.12 | 24h |
| `ENTITY` | 0.10 | 1h |
| `GENERAL` | 0.08 | 1h |
| `STRUCTURED` | 0.05 | 2h |

**Note:** These thresholds are RedisVL vector-distance cutoffs. The separate
store guard in `pipelines/client.py` uses `grade_confidence` on the **RRF scale**
(~0.0006 to 0.016), which is unrelated to cosine similarity.

### Non-Cacheable Query Types

`CHITCHAT` and `OFF_TOPIC` are not RAG-cacheable. They skip the semantic cache
path entirely. Structured catalog search uses separate catalog tooling and is
not a semantic response-cache type.

## Degradation Modes

### Mode 1: Cache Unavailable (Redis Down)

- Embeddings cache miss: re-encode on every request
- Semantic cache miss: proceed without caching
- **User impact:** Slower responses, no cache benefits
- **System behavior:** Graceful -- users still get answers

### Mode 2: Embedding Service Down (BGE-M3 Unreachable)

- Cannot compute embedding: bypass cache lookup entirely
- Proceed to full retrieval pipeline
- **User impact:** Full latency, no cache hit possible

### Mode 3: Qdrant Unavailable

- Cache hit: serve cached response (degraded freshness)
- Cache miss: fail with error
- **User impact:** Degraded quality on cache miss

## Cache Key Structure

```
# Semantic cache (RedisVL vector index)
Index: sem:v8:bge1024
Fields: query_text, query_type, language, user_id, cache_scope,
        agent_role, grounding_mode, filter_signature, response,
        semantic_cache_safe_reuse, response_state, cache_eligible,
        schema_version

# Embeddings cache (RedisVL)
Index: embeddings:v5
Fields: text (content), embedding (dense vector 1024-dim)

# Exact caches (redis-py SET/GET, JSON-serialized)
Key pattern: {tier}:{CACHE_VERSION}:{sha256_hash_16chars}
Examples: sparse:v5:a1b2c3d4e5f67890
          search:v5:f0e1d2c3b4a59687
          rerank:v5:1234567890abcdef
```

## Cache Scope

RAG semantic-cache checks and stores use `cache_scope="rag"`. History lookups
use `cache_scope="history"`. `CHITCHAT` and `OFF_TOPIC` skip the RAG path
before semantic cache lookup.

## Monitoring

| Metric | Description |
|--------|-------------|
| `cache_hit_total` | Total cache hits by type |
| `cache_miss_total` | Total cache misses by type |
| `cache_error_total` | Cache errors by tier |
| `cache_latency_ms` | Cache operation latency |

For debugging cache behavior, see the [Troubleshooting Guide](TROUBLESHOOTING_CACHE.md).

## Configuration

Environment variables:
- `REDIS_PASSWORD` -- Redis auth (required)
- `REDIS_URL` -- Redis connection URL
- `BGE_M3_URL` -- BGE-M3 embedding service URL (default: `http://bge-m3:8000`)

## Code Locations

| File | Purpose |
|------|---------|
| [`telegram_bot/integrations/cache.py`](../telegram_bot/integrations/cache.py) | `CacheLayerManager` -- all 5 tiers |
| `telegram_bot/services/cache_policy.py` | Cacheability decisions |
| `telegram_bot/graph/nodes/cache.py` | Graph cache lookup/store nodes |
| `telegram_bot/pipelines/client.py` | Client direct cache lookup/store flow |
