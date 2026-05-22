# Cache Degradation Behavior

> **Role:** Design behaviour -- cache tier architecture, degradation modes, and design rationale.
>
> | Related doc | Role |
> |---|---|
> | [TROUBLESHOOTING_CACHE.md](TROUBLESHOOTING_CACHE.md) | Debugging guide -- diagnose misses, inspect keys, read metrics |
> | [runbooks/REDIS_CACHE_DEGRADATION.md](runbooks/REDIS_CACHE_DEGRADATION.md) | Incident runbook -- operator response when Redis service fails |

Multi-tier semantic caching with graceful degradation when cache fails.

## Cache Tiers

`CacheLayerManager` in [`telegram_bot/integrations/cache.py`](../telegram_bot/integrations/cache.py)
implements five cache tiers plus a conversation store:

| # | Tier | Backend | Index / Key pattern | TTL |
|---|------|---------|---------------------|-----|
| 1 | Semantic | RedisVL SemanticCache | `sem:v8:bge1024` | Per query type |
| 2 | Embeddings | RedisVL EmbeddingsCache | `embeddings:v5` | 7 days |
| 3 | Sparse | Redis exact (SET/GET) | `sparse:v5:{hash}` | 7 days |
| 4 | Search | Redis exact (SET/GET) | `search:v5:{hash}` | 2 hours |
| 5 | Rerank | Redis exact (SET/GET) | `rerank:v5:{hash}` | 2 hours |
| 6 | Conversation | Redis LIST | `conversation:{user_id}` | 2 hours (20 msgs) |

The EmbeddingsCache (tier 2) also stores BGE-M3 query bundles (dense + sparse +
ColBERT as metadata in the same payload). This is an app-level optimization;
retrieval remains in Qdrant.

Version constants in source:

```
CACHE_VERSION = "v5"            # exact cache key prefix
SEMANTIC_CACHE_VERSION = "v8"   # semantic cache index prefix
```

## Per-Query-Type Thresholds

| Query Type | Distance Threshold | TTL | Rationale |
|------------|-------------------|-----|-----------|
| `FAQ` | 0.12 | 24 h | High precision required |
| `ENTITY` | 0.10 | 1 h | Entity/history-style specificity |
| `GENERAL` | 0.08 | 1 h | Balanced |
| `STRUCTURED` | 0.05 | 2 h | Most specific; strictest reuse |

Semantic thresholds are RedisVL vector-distance cutoffs; lower values are
stricter. The separate store guard uses `grade_confidence` on the RRF scale
(see [TROUBLESHOOTING_CACHE.md](TROUBLESHOOTING_CACHE.md) for common confusion).

`CHITCHAT` and `OFF_TOPIC` are not RAG-cacheable query types. Structured catalog
search uses separate catalog tooling.

## Degradation Modes

### Mode 1: Cache Unavailable (Redis Down)

- Embeddings cache miss: re-encode via BGE-M3 service
- Semantic cache miss: proceed without caching
- **User impact:** Slower response, no cache benefits
- **Monitoring:** `cache_errors` metric

### Mode 2: Embedding Service Down

- Cannot compute embedding: bypass cache lookup
- Proceed to full retrieval pipeline
- **User impact:** Full latency, no cache hit possible

### Mode 3: Qdrant Unavailable

- Cache hit: attempt to use cached response
- Cache miss: fail with error
- **User impact:** Degraded quality if cache miss

## Cache Key Structure

```
# Semantic result cache (RedisVL SemanticCache)
Index: sem:v8:bge1024
Schema: query_text, query_type, language, response, sources, metadata
Filterable: query_type, language, user_id, cache_scope, agent_role,
            grounding_mode, filter_signature, semantic_cache_safe_reuse,
            response_state, cache_eligible, schema_version

# Embeddings cache (RedisVL EmbeddingsCache)
Index: embeddings:v5
Schema: text (content), embedding (dense[1024])
```

## Cache Scope

RAG semantic-cache checks and stores use `cache_scope="rag"`; history lookups
use `cache_scope="history"`. `CHITCHAT` and `OFF_TOPIC` skip the RAG path before
semantic cache lookup.

## Configuration

Environment variables:

| Variable | Purpose |
|----------|---------|
| `REDIS_PASSWORD` | Redis auth (required) |
| `CACHE_TTL_DEFAULT` | Default TTL in seconds |
| `CACHE_EMBEDDING_TTL` | Embeddings cache TTL (default: 604800 = 7 days) |

## Source of Truth

| File | Purpose |
|------|---------|
| [`telegram_bot/integrations/cache.py`](../telegram_bot/integrations/cache.py) | CacheLayerManager (tier implementations, versions, TTLs) |
| [`telegram_bot/services/cache_policy.py`](../telegram_bot/services/cache_policy.py) | Cacheability decisions |
| [`telegram_bot/graph/nodes/cache.py`](../telegram_bot/graph/nodes/cache.py) | Graph cache lookup/store nodes |
| [`telegram_bot/pipelines/client.py`](../telegram_bot/pipelines/client.py) | Client direct cache lookup/store flow |
