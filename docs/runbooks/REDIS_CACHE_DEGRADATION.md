***REMOVED*** Runbook: Redis Cache Degradation

> **Owner:** Retrieval & Cache subsystems
> **Last verified:** 2026-05-07
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis redis-cli -a test-redis-password ping
> ```

Use this runbook when Redis cache issues affect RAG performance.

***REMOVED******REMOVED*** Symptoms

- Semantic cache not working (all queries miss)
- High latency despite cache hits
- Cache commands timing out
- `Redis connection refused` errors

***REMOVED******REMOVED*** Service / Container Map

| Compose service | Typical container names |
|---|---|
| `redis` | `dev-redis-1` (Compose v2+), `dev_redis_1` (legacy) |

> The app Redis is **distinct** from `redis-langfuse` (Langfuse v3 telemetry stack).
> If Langfuse shows Redis errors, verify whether the failing container is `redis` or `redis-langfuse` first.

***REMOVED******REMOVED*** Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an application bug.

***REMOVED******REMOVED******REMOVED*** 1. Container health and reachability

```bash
***REMOVED*** Check service status with deterministic CI env (read-only, no local .env required)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps redis

***REMOVED*** Test Redis connection from inside the container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis redis-cli -a test-redis-password ping
```

Expected: `PONG`.
If this fails, treat as **service failure** (container down, network partition, or auth misconfiguration at the Compose level).

***REMOVED******REMOVED******REMOVED*** 2. Read-only keyspace and memory inspection

```bash
***REMOVED*** Check key count and memory without scanning all keys
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis redis-cli -a test-redis-password DBSIZE

COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis redis-cli -a test-redis-password INFO memory
```

Look for:
- `used_memory_human` — near the 300M limit in `compose.yml` indicates memory pressure
- `maxmemory` — should match `256mb` (base) or `512mb` (dev override)
- `evicted_keys` > 0 — confirms aggressive eviction due to memory pressure

***REMOVED******REMOVED******REMOVED*** 3. Logs (read-only)

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs redis --tail=200
```

Check for:
- OOM killer messages
- Auth failures (`WRONGPASS`)
- Persistence errors (`Can't save in background`)

***REMOVED******REMOVED*** Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `redis-cli ping` from **inside** the container fails | Service failure | Restart container, check disk/memory on host |
| `redis-cli ping` works, but bot logs show `Connection refused` | App bug | Verify `REDIS_URL` in bot env; check password encoding |
| Redis memory is near limit and `evicted_keys` is rising | Service failure / capacity | Scale `maxmemory` or reduce TTL; see Remediation |
| Cache hit rate is 0% but Redis is healthy and has keys | App bug | Check semantic cache threshold, query_type mapping, or `CACHE_VERSION` drift in `telegram_bot/integrations/cache.py` |
| High latency **with** cache hits | App bug | Profile embedding or rerank tiers; latency may be upstream of Redis |
| Only specific tiers miss (e.g. `search` hits, `semantic` misses) | App bug | Inspect tier-specific TTLs and `distance_threshold` in source |

***REMOVED******REMOVED*** Source Paths

| Component | Path |
|---|---|
| Cache implementation | [`telegram_bot/integrations/cache.py`](../../telegram_bot/integrations/cache.py) |
| Redis service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides (ports, memory, password) | [`compose.dev.yml`](../../compose.dev.yml) |
| CI env fixture (deterministic interpolation) | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

***REMOVED******REMOVED*** Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs redis --tail=200` |
| Redis data volume | `redis_data` (managed volume, inspect with `docker volume inspect dev_redis_data`) |
| Bot cache metrics | Exposed via bot `/stats` command or Langfuse spans tagged `cache-semantic-check` |
| Memory trend | `INFO memory` sampled over time; sudden spikes correlate with ingestion batch writes |

***REMOVED******REMOVED*** Remediation

> ⚠️ **Caution:** Commands in this section mutate state. Run only after fast-path diagnosis confirms the issue is not an app bug.

***REMOVED******REMOVED******REMOVED*** Redis Connection Refused

1. Check if the Redis container is running:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps redis
   ```

2. Restart Redis:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart redis
   ```

3. Verify network connectivity from the bot container:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot redis-cli -h redis -a test-redis-password ping
   ```

***REMOVED******REMOVED******REMOVED*** Cache Corruption or Version Drift

If cache data appears corrupted or keys use an old `CACHE_VERSION` / `SEMANTIC_CACHE_VERSION`:

1. Clear caches programmatically (safe, uses SCAN not `KEYS *`):
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "
   import asyncio, os
   from telegram_bot.integrations.cache import CacheLayerManager
   async def clear():
       redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379')
       cache = CacheLayerManager(redis_url=redis_url)
       await cache.initialize()
       results = await cache.clear_all_caches()
       print(results)
   asyncio.run(clear())
   "
   ```

2. Or use the bot command: `/clearcache`

> **Avoid `KEYS *`** in production or large keyspaces. The `CacheLayerManager.clear_by_tier()` and `clear_semantic_cache()` methods use `SCAN` iteratively instead.

***REMOVED******REMOVED******REMOVED*** Memory Issues

1. Check memory usage:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis redis-cli -a test-redis-password INFO memory | grep used_memory_human
   ```

2. If near limit, consider:
   - Increasing `maxmemory` in `compose.dev.yml` (dev) or the host Redis config (production)
   - Reducing exact-cache TTLs in `telegram_bot/integrations/cache.py` (`DEFAULT_TTLS`)
   - Clearing old cache entries via tiered `clear_by_tier()`

***REMOVED******REMOVED*** Impact on Users

When Redis is down:
- **Semantic cache unavailable** — queries still work but no cache hits
- **Embeddings cache unavailable** — fresh embeddings computed each time
- **Session history unavailable** — new sessions don't retain context

The system degrades gracefully — users still get responses, just without cache benefits.

***REMOVED******REMOVED*** Prevention

- Monitor Redis memory: `redis-cli INFO memory`
- Set up alerting for `Redis connection refused` errors
- Regular cache health checks via `/stats` command
- Keep `compose.yml` and `compose.dev.yml` memory limits within host capacity

***REMOVED******REMOVED*** See Also

- [Qdrant Troubleshooting](QDRANT_TROUBLESHOOTING.md)
- [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
