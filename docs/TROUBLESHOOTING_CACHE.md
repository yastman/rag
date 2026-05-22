# Troubleshooting: Semantic Cache

> **Related docs:**
> - [Cache Degradation Behavior](CACHE_DEGRADATION.md) -- design and architecture of the 5-tier cache system
> - [Runbook: Redis Cache Degradation](runbooks/REDIS_CACHE_DEGRADATION.md) -- incident response for Redis service failures

This guide helps **debug cache behavior** when the cache is reachable but not
performing as expected (misses, staleness, threshold confusion). For Redis
service outages or container issues, use the
[incident runbook](runbooks/REDIS_CACHE_DEGRADATION.md) instead.

## Common Issues

### 1. Cache Always MISS Despite Correct Query

#### RRF Scale vs Cosine Similarity Confusion

The `grade_confidence` store guard in `pipelines/client.py` uses **RRF scale**
(~0.0006 to 0.016), NOT cosine similarity [0-1].

```python
grade_confidence >= config.relevance_threshold_rrf  # Default: 0.005
```

If your threshold is set to `0.8` thinking it is cosine similarity, nothing
will store.

**Fix:** Use RRF scale thresholds. A good starting point is `0.005`.

#### Cache Key Versioning

Each tier has a version prefix (see [Cache Degradation Behavior](CACHE_DEGRADATION.md) for the full key structure):

- `sem:v8:bge1024` -- Semantic cache index
- `embeddings:v5` -- Embeddings cache index
- `sparse:v5:` -- Sparse embeddings key prefix
- `search:v5:` -- Search results key prefix
- `rerank:v5:` -- Rerank results key prefix

When models change, bump the version in `telegram_bot/integrations/cache.py`:

```python
CACHE_VERSION = "v5"            # Bump to invalidate exact caches
SEMANTIC_CACHE_VERSION = "v8"   # Bump for semantic cache
```

### 2. Verifying Cache Checks

#### Langfuse Traces

Look for the `cache-semantic-check` span in Langfuse:

1. Find your trace
2. Look for "cache-semantic-check" span
3. Check output fields:
   - `hit`: true/false
   - `distance`: actual vector distance (lower = better match)
   - `threshold`: configured threshold for that query type

#### Bot Logs

```
# Cache hit:
Semantic HIT (Xms, dist=Y, threshold=Z, type=T)

# Cache miss:
Semantic MISS (Xms, type=T)

# Timeout:
Semantic cache timeout
```

### 3. Multi-Tier Debugging

Identify which tier is causing misses using per-tier metrics:

```python
stats = cache.get_metrics()
# Returns:
# {
#   "semantic": {"hits": N, "misses": N, "hit_rate": X},
#   "embeddings": {"hits": N, "misses": N, "hit_rate": X},
#   "sparse": {"hits": N, "misses": N, "hit_rate": X},
#   "search": {"hits": N, "misses": N, "hit_rate": X},
#   "rerank": {"hits": N, "misses": N, "hit_rate": X},
# }
```

### 4. Redis Key Inspection

```bash
# Connect to Redis
redis-cli -p 6379 -a "$REDIS_PASSWORD"

# Check semantic cache keys
KEYS sem:v8:*

# Check embedding cache
KEYS embeddings:v5:*

# Check exact cache keys
KEYS sparse:v5:*
KEYS search:v5:*
KEYS rerank:v5:*

# Inspect a semantic cache entry
GET "sem:v8:bge1024:somekey"
```

> For production or large keyspaces, prefer `SCAN` over `KEYS *`.

## Cache Poisoning and Staleness

### When to Bump Versions

| Trigger | Action |
|---------|--------|
| Embedding model change | Bump both `CACHE_VERSION` and `SEMANTIC_CACHE_VERSION` |
| LLM model version change | Bump `CACHE_VERSION` |
| Schema/filter change | Bump `SEMANTIC_CACHE_VERSION` |

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

For clearing via Docker Compose commands during an incident, see the
[incident runbook](runbooks/REDIS_CACHE_DEGRADATION.md#cache-corruption-or-version-drift).

## Cache vs Query Type Mapping

### Cacheable Query Types

Only these types are stored in semantic cache:

```python
_SEMANTIC_CACHEABLE_QUERY_TYPES = {"FAQ", "GENERAL", "ENTITY", "STRUCTURED"}
```

### Queries That Skip Cache

| Query Pattern | Reason |
|---------------|--------|
| Contextual follow-ups ("more details", "the first one", "this") | Different context each time |
| `CHITCHAT` / `OFF_TOPIC` | Not RAG queries |

### Cache Thresholds by Query Type

| Query Type | Distance Threshold | TTL |
|------------|-------------------|-----|
| `FAQ` | 0.12 | 24h |
| `ENTITY` | 0.10 | 1h |
| `GENERAL` | 0.08 | 1h |
| `STRUCTURED` | 0.05 | 2h |

## Monitoring

### Bot /metrics Command

Shows p50/p95 pipeline timing including cache performance.

### Langfuse Score: semantic_cache_hit

Track hit rate over time:

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
