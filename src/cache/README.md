***REMOVED*** 🚀 Redis Semantic Cache

This folder contains semantic caching implementation for RAG queries using Redis.

***REMOVED******REMOVED*** 📁 Contents

| File | Purpose |
|------|---------|
| `redis_semantic_cache.py` | Two-layer semantic cache with version-aware keys |

---

***REMOVED******REMOVED*** 🎯 Why Semantic Cache?

**Problem**: RAG queries are expensive and slow.
- Embedding generation: ~10ms + $0.00001 per query
- Vector search (Qdrant): ~50-200ms
- Total latency: 200-500ms per query

**Solution**: Cache results for semantically similar queries.
- Exact match: "Стаття 121 УК" → Cache hit
- Semantic match: "Стаття сто двадцять перша УК" → Cache hit (same meaning)

**Benefits**:
- **Latency**: 200-500ms → 2-5ms (100x faster)
- **Cost**: $0.00001/query → $0 (cached)
- **Load**: Reduces Qdrant traffic by 60-80%

---

***REMOVED******REMOVED*** 🏗️ Architecture

***REMOVED******REMOVED******REMOVED*** Two-Layer Cache

```
┌─────────────────────────────────────────────────────┐
│              User Query                             │
│    "Стаття 121 Кримінального кодексу"              │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1: Embedding Cache                           │
│  Key: embedding_v1.0.0_<query_hash>                 │
│  Value: [0.123, -0.456, ...]  (1024-dim vector)     │
│  TTL: 30 days                                       │
└────────────────┬────────────────────────────────────┘
                 │
                 │ Embedding exists? → Skip BGE-M3 call
                 ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Response Cache                            │
│  Key: response_v1.0.0_<query_hash>_<top_k>          │
│  Value: [{text: "...", score: 0.95}, ...]           │
│  TTL: 5-60 minutes (configurable)                   │
└─────────────────────────────────────────────────────┘
```

---

***REMOVED******REMOVED*** 📦 Redis Semantic Cache (`redis_semantic_cache.py`)

***REMOVED******REMOVED******REMOVED*** Key Features

1. **Two-layer caching**:
   - **Layer 1** (Embeddings): Saves BGE-M3 API calls (30-day TTL)
   - **Layer 2** (Responses): Saves Qdrant searches (5-60 min TTL)

2. **Version-aware keys**:
   - `embedding_v1.0.0_{hash}` → Invalidated when index rebuilt
   - `response_v1.0.0_{hash}_{top_k}` → Invalidated when config changes

3. **Metrics tracking**:
   - Cache hits/misses
   - Cost savings
   - Latency improvements

4. **OpenTelemetry integration**:
   - Traces for cache operations
   - Metrics exported to Prometheus

---

***REMOVED******REMOVED******REMOVED*** Usage

***REMOVED******REMOVED******REMOVED******REMOVED*** Initialize Cache

```python
from cache.redis_semantic_cache import RedisSemanticCache

***REMOVED*** Default: Automatically uses Docker network with REDIS_PASSWORD from environment
cache = RedisSemanticCache(
    index_version="1.0.0",  ***REMOVED*** Matches Qdrant collection version
    embedding_ttl_days=30,  ***REMOVED*** 30 days
    response_ttl_minutes=5, ***REMOVED*** 5 minutes
)

***REMOVED*** Or specify custom Redis URL
cache = RedisSemanticCache(
    redis_url="redis://:password@redis:6379/2",
    index_version="1.0.0",
)
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Example: RAG Query with Cache

```python
async def rag_query(query: str, top_k: int = 10):
    ***REMOVED*** 1. Try to get embedding from cache (Layer 1)
    embedding = await cache.get_embedding(query)

    if embedding is None:
        ***REMOVED*** Cache miss - generate embedding
        embedding = await bge_m3_client.embed(query)

        ***REMOVED*** Store in cache for future queries
        await cache.set_embedding(query, embedding)

    ***REMOVED*** 2. Try to get response from cache (Layer 2)
    cached_response = await cache.get_response(query, top_k)

    if cached_response is not None:
        ***REMOVED*** Cache hit! Return immediately
        return cached_response

    ***REMOVED*** 3. Cache miss - search Qdrant
    results = await qdrant_client.search(
        collection_name="contextual_rag_criminal_code_v1",
        query_vector=embedding,
        limit=top_k
    )

    ***REMOVED*** 4. Store response in cache
    await cache.set_response(query, top_k, results)

    return results
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Example: Get Cache Statistics

```python
stats = cache.get_stats()

print(f"Cache hits: {stats['hits']}")
print(f"Cache misses: {stats['misses']}")
print(f"Hit rate: {stats['hit_rate']:.1%}")
print(f"Cost saved: ${stats['cost_saved_usd']:.4f}")
print(f"Latency saved: {stats['latency_saved_ms']:.0f}ms")

***REMOVED*** Output:
***REMOVED*** Cache hits: 450
***REMOVED*** Cache misses: 150
***REMOVED*** Hit rate: 75.0%
***REMOVED*** Cost saved: $0.0045
***REMOVED*** Latency saved: 90000ms (90 seconds!)
```

---

***REMOVED******REMOVED******REMOVED*** Cache Key Design

***REMOVED******REMOVED******REMOVED******REMOVED*** Why Version in Key?

**Problem**: Stale cache after index rebuild.
- User queries "Стаття 121" before index rebuild
- Result cached with old index (missing new articles)
- User gets outdated results

**Solution**: Version-aware keys.
```python
***REMOVED*** Old index (v1.0.0)
embedding_key = "embedding_v1.0.0_abc123"
response_key = "response_v1.0.0_abc123_10"

***REMOVED*** New index (v1.0.1) - different keys!
embedding_key = "embedding_v1.0.1_abc123"
response_key = "response_v1.0.1_abc123_10"
```

When index version changes, **all cache keys become invalid** (automatic invalidation).

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Key Components

```python
***REMOVED*** Embedding cache key
key = f"embedding_v{version}_{query_hash}"
***REMOVED*** Example: "embedding_v1.0.0_5f4dcc3b"

***REMOVED*** Response cache key
key = f"response_v{version}_{query_hash}_{top_k}"
***REMOVED*** Example: "response_v1.0.0_5f4dcc3b_10"

***REMOVED*** Query hash (stable)
query_hash = hashlib.sha256(query.encode()).hexdigest()[:8]
```

---

***REMOVED******REMOVED******REMOVED*** Cache Invalidation Strategies

***REMOVED******REMOVED******REMOVED******REMOVED*** 1. Time-based (TTL)

```python
cache = RedisSemanticCache(
    embedding_ttl=2592000,  ***REMOVED*** 30 days
    response_ttl=300,       ***REMOVED*** 5 minutes
)
```

**Use Cases**:
- Embeddings: Long TTL (30 days) - stable
- Responses: Short TTL (5-60 min) - may change with index updates

---

***REMOVED******REMOVED******REMOVED******REMOVED*** 2. Version-based (Automatic)

```python
***REMOVED*** When index rebuilt
cache = RedisSemanticCache(
    index_version="1.0.1"  ***REMOVED*** Changed from "1.0.0"
)

***REMOVED*** All cache keys now use v1.0.1 → Old cache (v1.0.0) ignored
```

**Use Cases**:
- Index rebuilt (new articles added)
- Search algorithm changed (DBSF → ColBERT)
- Embedding model changed (bge-m3 → different version)

---

***REMOVED******REMOVED******REMOVED******REMOVED*** 3. Manual Invalidation

```python
***REMOVED*** Clear all cache
await cache.clear()

***REMOVED*** Clear specific query
await redis.delete(f"embedding_v1.0.0_{query_hash}")
await redis.delete(f"response_v1.0.0_{query_hash}_10")
```

---

***REMOVED******REMOVED*** 📊 Cache Performance

***REMOVED******REMOVED******REMOVED*** Expected Hit Rates

| Scenario | Expected Hit Rate |
|----------|-------------------|
| **Production** (repetitive queries) | 60-80% |
| **Development** (testing) | 10-30% |
| **First hour** (cold start) | 0-20% |
| **After 1 day** (warmed up) | 70-90% |

---

***REMOVED******REMOVED******REMOVED*** Cost Savings Calculation

```python
***REMOVED*** Assumptions
embedding_cost = 0.00001  ***REMOVED*** BGE-M3 per query
qdrant_search_cost = 0     ***REMOVED*** Self-hosted (no cost)
cache_hit_rate = 0.75      ***REMOVED*** 75%
queries_per_day = 10000

***REMOVED*** Savings
daily_queries_cached = queries_per_day * cache_hit_rate  ***REMOVED*** 7,500
daily_cost_saved = daily_queries_cached * embedding_cost  ***REMOVED*** $0.075
monthly_cost_saved = daily_cost_saved * 30               ***REMOVED*** $2.25

***REMOVED*** Latency savings
embedding_latency = 10     ***REMOVED*** ms
qdrant_latency = 200       ***REMOVED*** ms
cache_latency = 2          ***REMOVED*** ms

latency_saved_per_query = (embedding_latency + qdrant_latency) - cache_latency  ***REMOVED*** 208ms
daily_latency_saved = latency_saved_per_query * daily_queries_cached  ***REMOVED*** 1,560,000ms = 26 minutes
```

**Monthly Savings**:
- **Cost**: ~$2.25 (for BGE-M3 calls)
- **Latency**: ~13 hours of total user wait time

---

***REMOVED******REMOVED*** 🔌 Redis Configuration

***REMOVED******REMOVED******REMOVED*** Redis Setup

```bash
***REMOVED*** Docker Compose
services:
  redis:
    image: redis:8.2-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru  ***REMOVED*** Evict least recently used
      --save 60 1000                  ***REMOVED*** Snapshot every 60s if 1000 keys changed
```

**Access Redis**:
- Redis CLI: `docker exec -it redis redis-cli`
- Redis Commander: http://localhost:8081
- Redis Insight: http://localhost:8082

---

***REMOVED******REMOVED******REMOVED*** Redis Memory Policy

**allkeys-lru** (Least Recently Used):
- Redis evicts least recently used keys when memory full
- Best for cache workloads
- Keeps hot data in memory

**Alternative Policies**:
- `volatile-lru`: Only evict keys with TTL set
- `allkeys-lfu`: Least Frequently Used (better for some workloads)
- `volatile-ttl`: Evict keys with shortest TTL first

---

***REMOVED******REMOVED*** 🔍 Monitoring Cache

***REMOVED******REMOVED******REMOVED*** Redis Metrics

```bash
***REMOVED*** Connect to Redis
docker exec -it redis redis-cli

***REMOVED*** Get cache info
INFO stats
***REMOVED*** Look for:
***REMOVED***   keyspace_hits
***REMOVED***   keyspace_misses
***REMOVED***   used_memory
***REMOVED***   evicted_keys

***REMOVED*** Cache hit rate
HIT_RATE = keyspace_hits / (keyspace_hits + keyspace_misses)
```

---

***REMOVED******REMOVED******REMOVED*** Grafana Dashboard

Create dashboard with these queries:

***REMOVED******REMOVED******REMOVED******REMOVED*** Cache Hit Rate

```promql
***REMOVED*** Prometheus query
cache_hits / (cache_hits + cache_misses)
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Cache Size

```promql
redis_memory_used_bytes{instance="redis:6379"}
```

***REMOVED******REMOVED******REMOVED******REMOVED*** Eviction Rate

```promql
rate(redis_evicted_keys_total[5m])
```

---

***REMOVED******REMOVED******REMOVED*** Cache Stats in Application

```python
stats = cache.get_stats()

***REMOVED*** Log to console
logger.info(f"Cache stats: {stats}")

***REMOVED*** Export to Prometheus
from prometheus_client import Gauge

cache_hits_gauge = Gauge('rag_cache_hits_total', 'Total cache hits')
cache_misses_gauge = Gauge('rag_cache_misses_total', 'Total cache misses')
cache_hit_rate_gauge = Gauge('rag_cache_hit_rate', 'Cache hit rate')

cache_hits_gauge.set(stats['hits'])
cache_misses_gauge.set(stats['misses'])
cache_hit_rate_gauge.set(stats['hit_rate'])
```

---

***REMOVED******REMOVED*** 🚨 Troubleshooting

***REMOVED******REMOVED******REMOVED*** Issue: Cache hit rate < 20%

**Causes**:
1. TTL too short (responses expiring too quickly)
2. Index version changed (all keys invalidated)
3. Queries too diverse (no repetition)
4. Redis memory full (evicting keys)

**Solution**:
```bash
***REMOVED*** Check Redis memory
docker exec -it redis redis-cli INFO memory

***REMOVED*** Check eviction count
docker exec -it redis redis-cli INFO stats | grep evicted_keys

***REMOVED*** Increase memory limit
***REMOVED*** Edit docker-compose.yml:
command: redis-server --maxmemory 4gb  ***REMOVED*** Increase from 2gb

***REMOVED*** Increase response TTL
cache = RedisSemanticCache(response_ttl=1800)  ***REMOVED*** 30 minutes
```

---

***REMOVED******REMOVED******REMOVED*** Issue: Stale results after index update

**Cause**: Cache keys still using old version.

**Solution**: Increment index version.
```python
***REMOVED*** Old
cache = RedisSemanticCache(index_version="1.0.0")

***REMOVED*** New (after index rebuild)
cache = RedisSemanticCache(index_version="1.0.1")
```

All cache keys now use `v1.0.1` → Old cache (`v1.0.0`) ignored automatically.

---

***REMOVED******REMOVED******REMOVED*** Issue: Redis connection errors

**Cause**: Redis not running or connection refused.

**Solution**:
```bash
***REMOVED*** Check Redis is running
docker ps | grep redis

***REMOVED*** Test connection
docker exec -it redis redis-cli PING
***REMOVED*** Should return: PONG

***REMOVED*** Check connection from host
redis-cli -h localhost -p 6379 PING

***REMOVED*** Check network
docker network ls
docker network inspect contextual_rag_network
```

---

***REMOVED******REMOVED*** 📖 Best Practices

***REMOVED******REMOVED******REMOVED*** 1. Set Appropriate TTLs

```python
***REMOVED*** Production
cache = RedisSemanticCache(
    embedding_ttl=2592000,  ***REMOVED*** 30 days (stable)
    response_ttl=1800,      ***REMOVED*** 30 minutes (may change)
)

***REMOVED*** Development (shorter TTLs for testing)
cache = RedisSemanticCache(
    embedding_ttl=3600,     ***REMOVED*** 1 hour
    response_ttl=60,        ***REMOVED*** 1 minute
)
```

---

***REMOVED******REMOVED******REMOVED*** 2. Use Version-Aware Keys

```python
***REMOVED*** ✅ Good - version in key
key = f"response_v{index_version}_{query_hash}_{top_k}"

***REMOVED*** ❌ Bad - no version
key = f"response_{query_hash}_{top_k}"
```

---

***REMOVED******REMOVED******REMOVED*** 3. Monitor Cache Metrics

```python
***REMOVED*** Log stats every 100 queries
if query_count % 100 == 0:
    stats = cache.get_stats()
    logger.info(f"Cache hit rate: {stats['hit_rate']:.1%}")

    ***REMOVED*** Alert if hit rate drops
    if stats['hit_rate'] < 0.5:
        logger.warning(f"Low cache hit rate: {stats['hit_rate']:.1%}")
```

---

***REMOVED******REMOVED******REMOVED*** 4. Handle Cache Failures Gracefully

```python
try:
    cached_response = await cache.get_response(query, top_k)
except RedisError as e:
    logger.error(f"Cache error: {e}")
    cached_response = None  ***REMOVED*** Fall back to Qdrant

***REMOVED*** Continue without cache
if cached_response is None:
    results = await qdrant_client.search(...)
```

---

***REMOVED******REMOVED*** 🛠️ Configuration

***REMOVED******REMOVED******REMOVED*** Environment Variables

```bash
***REMOVED*** Redis connection (automatically used by RedisSemanticCache)
export REDIS_PASSWORD="your_password_here"  ***REMOVED*** Required for Docker setup
export REDIS_HOST="redis"                   ***REMOVED*** Default: redis (Docker network)
export REDIS_PORT="6379"                    ***REMOVED*** Default: 6379
export REDIS_CACHE_DB="2"                   ***REMOVED*** Default: 2 (separate from other uses)

***REMOVED*** Cache settings
export CACHE_INDEX_VERSION="1.0.0"
export CACHE_EMBEDDING_TTL_DAYS=30          ***REMOVED*** 30 days
export CACHE_RESPONSE_TTL_MINUTES=5         ***REMOVED*** 5 minutes

***REMOVED*** OpenTelemetry (for tracing)
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

---

***REMOVED******REMOVED******REMOVED*** Python Dependencies

```bash
pip install redis \
            opentelemetry-api \
            opentelemetry-sdk \
            opentelemetry-instrumentation-redis
```

---

***REMOVED******REMOVED*** 🚀 Quick Start

```bash
***REMOVED*** 1. Ensure Redis is running
docker ps | grep redis

***REMOVED*** 2. Initialize cache in your application
cd /srv/rag-fresh
source venv/bin/activate

python
>>> from cache.redis_semantic_cache import RedisSemanticCache
>>> cache = RedisSemanticCache(index_version="1.0.0")

***REMOVED*** 3. Use in RAG pipeline
>>> embedding = await cache.get_embedding("Стаття 121 УК")
>>> if embedding is None:
...     embedding = await bge_m3_client.embed("Стаття 121 УК")
...     await cache.set_embedding("Стаття 121 УК", embedding)

***REMOVED*** 4. Check stats
>>> stats = cache.get_stats()
>>> print(f"Hit rate: {stats['hit_rate']:.1%}")
```

---

***REMOVED******REMOVED*** 📊 Cache Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Two layers** | Embeddings stable (30d), responses may change (5-60min) |
| **Version in key** | Automatic invalidation on index rebuild |
| **Redis (not Memcached)** | Persistence, complex data structures, OpenTelemetry support |
| **SHA256 hash** | Stable, collision-resistant, deterministic |
| **allkeys-lru** | Cache workload, evict cold data automatically |

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team
