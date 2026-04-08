***REMOVED*** Runbook: Redis Cache Degradation

Use this runbook when Redis cache has issues affecting RAG performance.

***REMOVED******REMOVED*** Symptoms

- Semantic cache not working (all queries miss)
- High latency despite cache hits
- Cache commands timing out
- `Redis connection refused` errors

***REMOVED******REMOVED*** Diagnosis

***REMOVED******REMOVED******REMOVED*** 1. Check Redis Connectivity

```bash
***REMOVED*** Test Redis connection
docker compose exec redis redis-cli ping

***REMOVED*** Should return: PONG
```

***REMOVED******REMOVED******REMOVED*** 2. Check Redis Logs

```bash
docker compose logs redis --tail=100
```

***REMOVED******REMOVED******REMOVED*** 3. Verify Cache Keyspace

```bash
***REMOVED*** Connect to Redis
docker compose exec redis redis-cli

***REMOVED*** List all keys (use with caution in production)
KEYS *

***REMOVED*** Check key counts by type
DBSIZE

***REMOVED*** Check memory usage
INFO memory | grep used_memory_human
```

***REMOVED******REMOVED******REMOVED*** 4. Test Cache Operations

```python
***REMOVED*** Test semantic cache
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://localhost:6379")
await cache.initialize()

***REMOVED*** Check semantic cache
result = await cache.check_semantic(
    query="test query",
    vector=[0.1] * 1024,
    query_type="FAQ"
)
print(f"Cache result: {result}")
```

***REMOVED******REMOVED*** Remediation

***REMOVED******REMOVED******REMOVED*** Redis Connection Refused

1. Check if Redis container is running:
   ```bash
   docker compose ps redis
   ```

2. Restart Redis:
   ```bash
   docker compose restart redis
   ```

3. Verify network connectivity:
   ```bash
   docker compose exec bot redis-cli -h redis ping
   ```

***REMOVED******REMOVED******REMOVED*** Cache Corruption

If cache data appears corrupted:

1. Clear all caches:
   ```bash
   docker compose exec bot python -c "
   import asyncio
   from telegram_bot.integrations.cache import CacheLayerManager
   async def clear():
       cache = CacheLayerManager(redis_url='redis://redis:6379')
       await cache.initialize()
       results = await cache.clear_all_caches()
       print(results)
   asyncio.run(clear())
   "
   ```

2. Or use bot command: `/clearcache`

***REMOVED******REMOVED******REMOVED*** Memory Issues

1. Check memory usage:
   ```bash
   docker compose exec redis redis-cli INFO memory | grep used_memory_human
   ```

2. If near limit, consider:
   - Increasing `maxmemory` in Redis config
   - Clearing old cache entries

***REMOVED******REMOVED*** Impact on Users

When Redis is down:
- **Semantic cache unavailable** — queries still work but no cache hits
- **Embeddings cache unavailable** — fresh embeddings computed each time
- **Session history unavailable** — new sessions don't retain context

The system degrades gracefully — users still get responses, just without cache benefits.

***REMOVED******REMOVED*** Prevention

- Monitor Redis memory: `redis INFO memory`
- Set up alerting for `Redis connection refused` errors
- Regular cache health checks via `/stats` command
