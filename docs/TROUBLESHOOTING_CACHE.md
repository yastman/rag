# Troubleshooting: Semantic Cache

> **Role:** Debugging guide -- diagnose cache misses, inspect keys, read metrics, and resolve staleness.
>
> | Related doc | Role |
> |---|---|
> | [CACHE_DEGRADATION.md](CACHE_DEGRADATION.md) | Design behaviour -- tier architecture, degradation modes, thresholds |
> | [runbooks/REDIS_CACHE_DEGRADATION.md](runbooks/REDIS_CACHE_DEGRADATION.md) | Incident runbook -- operator response when Redis service fails |

This guide helps debug cache behavior in `CacheLayerManager`
([`telegram_bot/integrations/cache.py`](../telegram_bot/integrations/cache.py)).
For tier design and degradation modes, see
[CACHE_DEGRADATION.md](CACHE_DEGRADATION.md).

## Common Issues

### 1. Cache Always MISS Despite Correct Query

**Symptoms:** Every query results in cache miss, even repeated identical queries.

**Causes and solutions:**

#### RRF Scale vs Cosine Similarity Confusion

The `grade_confidence` threshold uses **RRF scale** (~0.0006 to 0.016), NOT
cosine similarity [0-1].

The store guard in `pipelines/client.py` requires:

```python
grade_confidence >= config.relevance_threshold_rrf  # Default: 0.005
```

If your threshold is set to `0.8` thinking it is cosine similarity, nothing will
store.

**Fix:** Use RRF scale thresholds. A good starting point is `0.005`.

#### Cache Key Versioning

Each tier has a version prefix:

- `sem:v8:` / index `sem:v8:bge1024` -- Semantic cache
- `embeddings:v5` -- Embeddings (RedisVL EmbeddingsCache)
- `sparse:v5:` -- Sparse embeddings
- `search:v5:` -- Search results
- `rerank:v5:` -- Reranked results

When models change, bump the version in `integrations/cache.py`:

```python
CACHE_VERSION = "v5"  # Bump to invalidate exact caches
SEMANTIC_CACHE_VERSION = "v8"  # Bump for semantic cache
```

For full tier design details, see
[CACHE_DEGRADATION.md - Cache Tiers](CACHE_DEGRADATION.md#cache-tiers).

### 2. How to Verify Cache is Being Checked

Check Langfuse traces for `cache-semantic-check` span:

```
In Langfuse UI:
1. Find your trace
2. Look for "cache-semantic-check" span
3. Check output fields:
   - hit: true/false
   - distance: actual vector distance (lower = better match)
   - threshold: configured threshold
```

Or check bot logs for cache hit/miss:

```
# Cache hit log:
Semantic HIT (Xms, dist=Y, threshold=Z, type=T)

# Cache miss log:
Semantic MISS (Xms, type=T)
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
SCAN 0 MATCH "sem:v8:bge1024:*" COUNT 100

# Check embedding cache
SCAN 0 MATCH "embeddings:v5:*" COUNT 100

# Check search cache
SCAN 0 MATCH "search:v5:*" COUNT 100
```

> **Avoid `KEYS *`** in production or large keyspaces. Use `SCAN` instead.

## Cache Poisoning / Staleness

### When Version Bump Happens

| Trigger | Action |
|---------|--------|
| Model version change | Bump `CACHE_VERSION` |
| Embedding model change | Bump `CACHE_VERSION` + `SEMANTIC_CACHE_VERSION` |
| Schema change | Bump `SEMANTIC_CACHE_VERSION` |

### Manual Cache Clear

For cache clear commands and procedures (programmatic, CLI, and bot command),
see [runbooks/REDIS_CACHE_DEGRADATION.md - Cache Corruption or Version Drift](runbooks/REDIS_CACHE_DEGRADATION.md#cache-corruption-or-version-drift).

## Cache vs Query Type Mapping

### Cacheable Query Types

Only these types are stored in semantic cache:

```python
_SEMANTIC_CACHEABLE_QUERY_TYPES = {"FAQ", "GENERAL", "ENTITY", "STRUCTURED"}
```

### Queries That Skip Cache

| Query Pattern | Reason |
|---------------|--------|
| Contextual follow-ups ("more details", "the first one", "this") | Different context |
| CHITCHAT / OFF_TOPIC | Not RAG queries |

### Cache Thresholds and TTLs by Query Type

See the authoritative table in
[CACHE_DEGRADATION.md - Per-Query-Type Thresholds](CACHE_DEGRADATION.md#per-query-type-thresholds).

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
