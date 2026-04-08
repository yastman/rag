# Runbook: Redis Cache Degradation

Use this runbook when Redis cache has issues affecting RAG performance.

## Symptoms

- Semantic cache not working (all queries miss)
- High latency despite cache hits
- Cache commands timing out
- `Redis connection refused` errors

## Diagnosis

### 1. Check Redis Connectivity

```bash
# Test Redis connection
docker compose exec redis redis-cli ping

# Should return: PONG
```

### 2. Check Redis Logs

```bash
docker compose logs redis --tail=100
```

### 3. Verify Cache Keyspace

```bash
# Connect to Redis
docker compose exec redis redis-cli

# List all keys (use with caution in production)
KEYS *

# Check key counts by type
DBSIZE

# Check memory usage
INFO memory | grep used_memory_human
```

### 4. Test Cache Operations

```python
# Test semantic cache
from telegram_bot.integrations.cache import CacheLayerManager

cache = CacheLayerManager(redis_url="redis://localhost:6379")
await cache.initialize()

# Check semantic cache
result = await cache.check_semantic(
    query="test query",
    vector=[0.1] * 1024,
    query_type="FAQ"
)
print(f"Cache result: {result}")
```

## Remediation

### Redis Connection Refused

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

### Cache Corruption

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

### Memory Issues

1. Check memory usage:
   ```bash
   docker compose exec redis redis-cli INFO memory | grep used_memory_human
   ```

2. If near limit, consider:
   - Increasing `maxmemory` in Redis config
   - Clearing old cache entries

## Impact on Users

When Redis is down:
- **Semantic cache unavailable** — queries still work but no cache hits
- **Embeddings cache unavailable** — fresh embeddings computed each time
- **Session history unavailable** — new sessions don't retain context

The system degrades gracefully — users still get responses, just without cache benefits.

## Prevention

- Monitor Redis memory: `redis INFO memory`
- Set up alerting for `Redis connection refused` errors
- Regular cache health checks via `/stats` command
