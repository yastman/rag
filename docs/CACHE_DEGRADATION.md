# Cache Degradation Behavior

> **Scope:** Design and architecture of the multi-tier cache system and its
> graceful degradation modes.
>
> Related docs:
> - [Troubleshooting Cache](TROUBLESHOOTING_CACHE.md) - debugging guide for cache issues
> - [Redis Cache Degradation Runbook](runbooks/REDIS_CACHE_DEGRADATION.md) - operator incident runbook

## Cache Tiers

The `CacheLayerManager` (`telegram_bot/integrations/cache.py`) implements a
5-tier Redis cache for the RAG pipeline:

| # | Tier | Type | Index / Prefix | TTL |
|---|------|------|----------------|-----|
| 1 | Semantic | RedisVL SemanticCache | `sem:v8:bge1024` | Per query type |
| 2 | Embeddings | RedisVL EmbeddingsCache | `embeddings:v5` | 7 days |
| 3 | Sparse | Redis exact | `sparse:v5:` | 7 days |
| 4 | Search | Redis exact | `search:v5:` | 2 hours |
| 5 | Rerank | Redis exact | `rerank:v5:` | 2 hours |

Additionally, conversation history is stored as a Redis LIST (20 messages max,
2h TTL) keyed by `conversation:<user_id>`.

Version constants in source: `CACHE_VERSION = "v5"`, `SEMANTIC_CACHE_VERSION = "v8"`.

### Tier Details

**Semantic cache** - Skips retrieval + generation for similar queries. Uses
BGE-M3 1024-dim embeddings with per-query-type distance thresholds.

**Embeddings cache** - Skips re-encoding of repeated queries. Stores dense
vectors and BGE-M3 query-bundle payload.

**Sparse cache** - Stores sparse embedding vectors to avoid recomputation.

**Search cache** - Stores Qdrant search results to skip repeated retrieval.

**Rerank cache** - Stores reranked results to skip repeated reranking.

## Per-Query-Type Thresholds

| Query Type | Distance Threshold | TTL | Rationale |
|------------|-------------------|-----|-----------|
| `FAQ` | 0.12 | 24h | High precision required |
| `ENTITY` | 0.10 | 1h | Entity/history-style specificity |
| `GENERAL` | 0.08 | 1h | Balanced |
| `STRUCTURED` | 0.05 | 2h | Most specific; strictest reuse |

**Note:** Semantic thresholds are RedisVL vector-distance cutoffs; lower values
are stricter. The separate store guard still uses `grade_confidence` on the RRF
scale.

`CHITCHAT` and `OFF_TOPIC` are not RAG cacheable query types. Structured catalog
search uses separate catalog tooling and should not be documented as a semantic
response-cache type unless the runtime policy changes.

## Degradation Modes

### Mode 1: Cache Unavailable (Redis Down)

- All exact caches (embeddings, sparse, search, rerank) miss - recompute
- Semantic cache miss - proceed without caching
- **User impact:** Slower response, no cache benefits
- **Monitoring:** `cache_errors` metric

### Mode 2: Embedding Service Down

- Cannot compute embedding - bypass semantic and embeddings cache lookup
- Proceed to full retrieval pipeline
- **User impact:** Full latency, no cache hit possible

### Mode 3: Qdrant Unavailable

- Cache hit - attempt to use cached response
- Cache miss - fail with error
- **User impact:** Degraded quality if cache miss

The system degrades gracefully in all modes: users still get responses, just
without cache benefits. See the
[incident runbook](runbooks/REDIS_CACHE_DEGRADATION.md) for remediation steps.

## Cache Key Structure

```
# Semantic result cache
Index: sem:v8:bge1024
Schema: query_text, query_type, language, response, sources, metadata

# Embeddings cache
Index: embeddings:v5
Schema: text (str), embedding (dense[1024])

# Exact caches use key format: <tier>:<CACHE_VERSION>:<hash>
# e.g. sparse:v5:<sha256_prefix>, search:v5:<sha256_prefix>, rerank:v5:<sha256_prefix>
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

For debugging cache behavior (inspecting keys, verifying hits), see the
[Troubleshooting Cache](TROUBLESHOOTING_CACHE.md) guide.

## Configuration

Environment variables:
- `REDIS_PASSWORD` - Redis auth (required)
- `CACHE_TTL_DEFAULT` - Default TTL in seconds
- `CACHE_EMBEDDING_TTL` - Embeddings cache TTL (default: 604800 = 7 days)

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/integrations/cache.py` | CacheLayerManager (5-tier manager) |
| `telegram_bot/services/cache_policy.py` | Cacheability decisions |
| `telegram_bot/graph/nodes/cache.py` | Graph cache lookup/store nodes |
| `telegram_bot/pipelines/client.py` | Client direct cache lookup/store flow |
