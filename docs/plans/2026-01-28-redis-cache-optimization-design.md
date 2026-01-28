# Redis Cache Optimization Design

**Date:** 2026-01-28
**Status:** Draft
**Author:** Claude + User

## Summary

Optimize Redis caching layer for production: upgrade to Redis 8.4, fix key versioning, calibrate distance thresholds for Russian language, add monitoring.

## Current State Analysis

### Redis Container
- **Image:** `redis/redis-stack:latest` (needs restart to `redis:8.4.0`)
- **Memory:** 4.73M / 512MB used
- **Eviction:** `allkeys-lfu` ✓

### Cache Namespaces (28 keys total)

| Prefix | Count | Problem |
|--------|-------|---------|
| `rag_llm_cache:` | 3 | No model version in name |
| `bge_m3_embeddings:` | 7 | **Wrong name** — actually uses Voyage/USER-base |
| `sparse:bm42:` | ~5 | OK |
| `rag:analysis:v1:` | ~5 | OK |
| `rag:search:v1:v1:` | ~5 | Double `v1:v1:` bug |
| `rag:rerank:v1:` | ~3 | OK |

### Critical Issues

1. **Model mismatch in EmbeddingsCache name:** `bge_m3_embeddings` but uses Voyage (1024-dim) or USER-base (768-dim)
2. **No vectorizer version in SemanticCache:** Mixing USER-base (768-dim) and Voyage (1024-dim) causes garbage matches
3. **distance_threshold=0.20 not calibrated:** May cause false positives for Russian paraphrases
4. **No CACHE_SCHEMA_VERSION:** Model changes silently poison cache

---

## Design: Best Practices 2026

### 1. Cache Key Versioning (Redis Best Practice #4)

**Source:** [Redis 10 Techniques for Semantic Cache Optimization](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)

Add `CACHE_SCHEMA_VERSION` + `vectorizer_id` to all cache names:

```python
# Constants at top of cache.py
CACHE_SCHEMA_VERSION = "v2"

def _get_vectorizer_id(self) -> str:
    """Get vectorizer identifier for cache namespacing."""
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
    if use_local:
        return "userbase768"  # deepvk/USER-base, 768-dim
    return "voyage1024"  # voyage-multilingual-2, 1024-dim
```

**New cache names:**

| Old | New |
|-----|-----|
| `rag_llm_cache` | `sem:{version}:{vectorizer}` → `sem:v2:userbase768` |
| `bge_m3_embeddings` | `emb:{version}:{model}` → `emb:v2:voyage4` |
| `rag:search:v1:v1:` | `search:{version}:` → `search:v2:` |

### 2. Distance Threshold Calibration (Redis Best Practice #4)

**Source:** [RedisVL Threshold Optimization](https://redis.io/docs/latest/develop/ai/redisvl/user_guide/threshold_optimization/)

Current: `distance_threshold=0.20` (cosine distance, not calibrated)

**Recommendation:** Use `CacheThresholdOptimizer` with Russian test data:

```python
from redisvl.utils.optimize import CacheThresholdOptimizer

# Russian paraphrase test data
test_data = [
    {"query": "квартира в центре", "query_match": ""},  # No match expected
    {"query": "двушка в центре города", "query_match": key1},  # Match expected
    {"query": "2-комнатная квартира центр", "query_match": key1},  # Match expected
    {"query": "погода в Москве", "query_match": ""},  # No match (different topic)
]

optimizer = CacheThresholdOptimizer(semantic_cache, test_data)
optimizer.optimize()
# Expected: threshold drops from 0.20 to ~0.10-0.15
```

**Fallback for USER-base (768-dim):** Start with `0.15` (stricter than 0.20)

### 3. Adaptive TTL Strategy (Redis Best Practice #7)

**Source:** [Redis 10 Techniques](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)

Keep current TTLs (reasonable), but document rationale:

| Cache Type | TTL | Rationale |
|------------|-----|-----------|
| Semantic (LLM answers) | 48h | Answers may become stale |
| Embeddings | 7d | Model doesn't change often |
| Search results | 2h | Index may be updated |
| Rerank | 2h | Same as search |
| Analyzer | 24h | Filters are stable |

**Add eviction monitoring:**
```python
async def get_eviction_stats(self) -> dict:
    """Get Redis eviction statistics."""
    info = await self.redis_client.info("stats")
    return {
        "evicted_keys": info.get("evicted_keys", 0),
        "expired_keys": info.get("expired_keys", 0),
    }
```

### 4. Metadata Filtering (Redis Best Practice #6)

**Current:** `filterable_fields=[user_id, language, query_type]` ✓

**Keep as-is** — already implements multi-tenant isolation.

### 5. Monitoring Metrics (Redis Best Practice #8)

**Current:** Basic hit/miss counters ✓

**Add:**
- Per-layer hit rates (already have)
- Eviction count
- Memory usage
- False-hit detection (sample validation)

```python
async def get_full_metrics(self) -> dict:
    """Get comprehensive cache metrics."""
    base_metrics = self.get_metrics()

    # Add Redis stats
    info = await self.redis_client.info("memory")
    stats = await self.redis_client.info("stats")

    return {
        **base_metrics,
        "redis": {
            "used_memory_human": info.get("used_memory_human"),
            "maxmemory_human": info.get("maxmemory_human"),
            "evicted_keys": stats.get("evicted_keys", 0),
            "keyspace_hits": stats.get("keyspace_hits", 0),
            "keyspace_misses": stats.get("keyspace_misses", 0),
        }
    }
```

---

## Implementation Plan

### Phase 1: Redis Container Upgrade (Immediate)

1. Restart Redis with `redis:8.4.0`
2. Run `make test-redis` to verify Query Engine
3. Verify existing keys still accessible

### Phase 2: Cache Key Versioning (Code Changes)

1. Add `CACHE_SCHEMA_VERSION = "v2"` constant
2. Add `_get_vectorizer_id()` method
3. Update SemanticCache name: `sem:v2:{vectorizer_id}`
4. Update EmbeddingsCache name: `emb:v2:{model}`
5. Fix double `v1:v1:` in search cache keys
6. **Migration:** Old keys will naturally expire (TTL), no manual cleanup needed

### Phase 3: Threshold Calibration (Testing)

1. Create Russian paraphrase test dataset (20-30 pairs)
2. Run `CacheThresholdOptimizer`
3. Update default `distance_threshold` based on results
4. Add threshold to cache name for versioning

### Phase 4: Monitoring (Observability)

1. Add `get_full_metrics()` method
2. Add eviction tracking
3. Log metrics on bot startup and periodically

---

## File Changes

| File | Changes |
|------|---------|
| `telegram_bot/services/cache.py` | Add versioning, fix names, add metrics |
| `docker-compose.dev.yml` | Already updated to `redis:8.4.0` |
| `docker-compose.local.yml` | Already updated to `redis:8.4.0` |
| `tests/unit/services/test_cache.py` | Add tests for new cache names |

---

## Migration Strategy

**No manual migration needed:**
- Old keys (`rag_llm_cache:*`, `bge_m3_embeddings:*`) will expire naturally (TTL 48h-7d)
- New keys use new prefixes (`sem:v2:*`, `emb:v2:*`)
- No data loss — just gradual replacement

**Optional cleanup (if needed):**
```bash
# Delete old keys (only if memory pressure)
docker exec dev-redis redis-cli --scan --pattern "bge_m3_embeddings:*" | xargs -r docker exec -i dev-redis redis-cli DEL
docker exec dev-redis redis-cli --scan --pattern "rag_llm_cache:*" | xargs -r docker exec -i dev-redis redis-cli DEL
```

---

## Testing Checklist

- [ ] Redis 8.4.0 container running
- [ ] `make test-redis` passes
- [ ] New cache keys created with `v2` prefix
- [ ] Old keys still readable (backward compat during migration)
- [ ] SemanticCache hit rate reasonable (>30%)
- [ ] No false positives on unrelated queries
- [ ] Metrics endpoint returns Redis stats

---

## References

- [Redis 10 Techniques for Semantic Cache Optimization](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)
- [RedisVL Threshold Optimization](https://redis.io/docs/latest/develop/ai/redisvl/user_guide/threshold_optimization/)
- [RedisVL SemanticCache API](https://docs.redisvl.com/en/latest/api/cache.html)
- [Redis 8.4 What's New](https://redis.io/docs/latest/develop/whats-new/8-4/)
