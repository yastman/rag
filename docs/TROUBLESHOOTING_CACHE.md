# Troubleshooting: Semantic Cache

The semantic cache is a multi-tier system (`CacheLayerManager` in `telegram_bot/integrations/cache.py`). This guide helps debug cache behavior.

## Cache Architecture

The `CacheLayerManager` implements 5 cache tiers:

| Tier | Type | TTL | Purpose |
|------|------|-----|---------|
| Semantic | RedisVL SemanticCache | Query-type dependent | LLM response caching |
| Embeddings | RedisVL EmbeddingsCache | 7 days | Dense embedding cache |
| Sparse | Redis exact | 7 days | Sparse embedding cache |
| Search | Redis exact | 2 hours | Search results cache |
| Rerank | Redis exact | 2 hours | Reranked results cache |

## Common Issues

### 1. Cache Always MISS Despite Correct Query

**Symptoms:** Every query results in cache miss, even repeated identical queries.

**Causes and solutions:**

#### RRF Scale vs Cosine Similarity Confusion

The `grade_confidence` threshold uses **RRF scale** (~0.0006 to 0.016), NOT cosine similarity [0-1].

The store guard in `pipelines/client.py` requires:
```python
grade_confidence >= config.relevance_threshold_rrf  # Default: 0.005
```

If your threshold is set to `0.8` thinking it's cosine similarity, nothing will store.

**Fix:** Use RRF scale thresholds. A good starting point is `0.005`.

#### Cache Key Versioning

Each tier has a version prefix:
- `sem:v5:` — Semantic cache
- `embeddings:v5:` — Embeddings
- `sparse:v5:` — Sparse embeddings
- `search:v5:` — Search results

When models change, bump the version in `integrations/cache.py`:
```python
CACHE_VERSION = "v6"  # Bump to invalidate old cache
SEMANTIC_CACHE_VERSION = "v8"  # Bump for semantic cache
```

### 2. How to Verify Cache is Being Checked

Check Langfuse traces for `cache-semantic-check` span:

```python
# In Langfuse UI:
# 1. Find your trace
# 2. Look for "cache-semantic-check" span
# 3. Check output fields:
#    - hit: true/false
#    - distance: actual RRF distance (lower = better match)
#    - threshold: configured threshold
```

Or check bot logs for cache hit/miss:

```python
# Cache hit log:
logger.info("Semantic HIT (%.0fms, dist=%.3f, threshold=%.2f, type=%s)", ...)

# Cache miss log:
logger.debug("Semantic MISS (%.0fms, type=%s)", ...)
```

### 3. Multi-Tier Cache Debugging

To identify which tier is causing misses:

```python
# Get per-tier metrics
stats = cache.get_metrics()
# Returns:
# {
#   "semantic": {"hits": N, "misses": N, "hit_rate": X},
#   "embeddings": {"hits": N, "misses": N, "hit_rate": X},
#   ...
# }
```

### 4. Redis Key Inspection

```bash
# Connect to Redis
redis-cli -p 6379 -a "$REDIS_PASSWORD"

# Check semantic cache keys
KEYS sem:v5:*

# Check embedding cache
KEYS embeddings:v5:*

# Check search cache
KEYS search:v5:*

# Inspect a semantic cache entry
GET "sem:v5:bge1024:somekey"
```

## Cache Poisoning / Staleness

### When Version Bump Happens

| Trigger | Action |
|---------|--------|
| Model version change | Bump `CACHE_VERSION` |
| Embedding model change | Bump `CACHE_VERSION` + `SEMANTIC_CACHE_VERSION` |
| Schema change | Bump `SEMANTIC_CACHE_VERSION` |

### Manual Cache Clear

```python
# Clear specific tier
await cache.clear_by_tier("embeddings")

# Clear semantic cache
await cache.clear_semantic_cache()

# Clear all tiers
results = await cache.clear_all_caches()
# Returns: {"semantic": N, "embeddings": N, "sparse": N, ...}
```

Or via bot command: `/clearcache`

## Cache vs Query Type Mapping

### Cacheable Query Types

Only these types are stored in semantic cache:

```python
_PIPELINE_STORE_TYPES = {"FAQ", "GENERAL", "ENTITY"}
```

### Queries That Skip Cache

| Query Pattern | Reason |
|---------------|--------|
| Contextual follow-ups ("подробнее", "первый", "это", "ещё") | Different context |
| STRUCTURED queries | Too specific to cache |
| CHITCHAT/OFF_TOPIC | Not RAG queries |

### Cache Thresholds by Query Type

| Query Type | Distance Threshold | TTL |
|------------|-------------------|-----|
| FAQ | 0.12 | 24h |
| ENTITY | 0.10 | 1h |
| GENERAL | 0.08 | 1h |
| STRUCTURED | 0.05 | 2h |

## Metrics and Monitoring

### Bot /metrics Command

Shows p50/p95 pipeline timing including cache performance.

### Langfuse Score: semantic_cache_hit

Track over time:
```sql
SELECT
  date_trunc('hour', timestamp),
  AVG(CASE WHEN name = 'semantic_cache_hit' AND value = 1 THEN 1.0 ELSE 0.0 END) as hit_rate
FROM scores
WHERE name = 'semantic_cache_hit'
GROUP BY 1
```

### Log Indicators

| Log Message | Meaning |
|-------------|---------|
| `Semantic HIT (Xms, dist=Y, threshold=Z)` | Cache hit |
| `Semantic MISS (Xms, type=Y)` | Cache miss |
| `Semantic cache timeout` | Cache check exceeded 0.3s |
| `Store semantic: ...` | Response stored |
