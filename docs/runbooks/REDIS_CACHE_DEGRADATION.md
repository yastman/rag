# Runbook: Redis Cache Degradation

> **Related docs:**
> - [Cache Degradation Behavior](../CACHE_DEGRADATION.md) -- design and architecture of the 5-tier cache system
> - [Troubleshooting: Semantic Cache](../TROUBLESHOOTING_CACHE.md) -- debugging guide for cache misses, thresholds, and monitoring

> **Owner:** Retrieval & Cache subsystems
> **Last verified:** 2026-05-12
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" ping'
> ```

Use this runbook when **Redis service issues** affect RAG performance (connection
failures, timeouts, memory pressure, container problems). For application-level
cache debugging (wrong thresholds, unexpected misses, cache poisoning), use the
[Troubleshooting Guide](../TROUBLESHOOTING_CACHE.md) instead.

## Symptoms

- Semantic cache not working (all queries miss)
- High latency despite cache hits
- Cache commands timing out
- `Redis connection refused` errors

## Service / Container Map

| Compose service | Typical container names | Notes |
|---|---|---|
| `redis` | `dev-redis-1` (Compose v2+), `dev_redis_1` (legacy) | App cache used by bot runtime, `CacheLayerManager`, and LangGraph |
| `redis-langfuse` | `dev-redis-langfuse-1`, `dev_redis_langfuse_1` | Langfuse internal telemetry (separate service) |

> The app Redis (`redis`) is **distinct** from `redis-langfuse`.
> If Langfuse shows Redis errors, verify which container is failing first.
> `redis` is currently pinned to Redis **8.6.3** in compose.

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an
application bug.

### 1. Container health and reachability

```bash
# Check service status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps redis

# Test Redis connection from inside the container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" ping'
```

Expected: `PONG`.
If this fails, treat as **service failure** (container down, network partition,
or auth misconfiguration).

### 1b. Verify container/runtime version

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" INFO server | grep "^redis_version"'
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis-langfuse sh -lc 'if [ -n "${LANGFUSE_REDIS_PASSWORD:-}" ]; then redis-cli -a "$LANGFUSE_REDIS_PASSWORD" INFO server; else redis-cli INFO server; fi | grep "^redis_version"'
```

### 2. Keyspace and memory inspection

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" DBSIZE'

COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" INFO memory'
```

Look for:
- `used_memory_human` -- compare against `deploy.resources.limits.memory` in [`compose.yml`](../../compose.yml)
- `maxmemory` -- verify against [`compose.yml`](../../compose.yml) and [`compose.dev.yml`](../../compose.dev.yml); canonical values in [`DOCKER.md`](../../DOCKER.md)
- `evicted_keys` > 0 -- confirms memory pressure

### 3. Logs

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs redis --tail=200
```

Check for: OOM killer messages, `WRONGPASS` auth failures, persistence errors.

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| `redis-cli ping` from inside container fails | Service failure | Restart container, check disk/memory |
| `redis-cli ping` works, bot logs show `Connection refused` | App bug | Verify `REDIS_URL` in bot env; check password encoding |
| Bot preflight shows `WRONGPASS` / `NOAUTH` after `.env` edit | Local auth drift | Run `make local-redis-recreate` then `make test-bot-health` |
| Memory near limit and `evicted_keys` rising | Capacity issue | Scale `maxmemory` or reduce TTL |
| Cache hit rate 0% but Redis healthy with keys | App bug | See [Troubleshooting Guide](../TROUBLESHOOTING_CACHE.md) for threshold/version drift |
| High latency with cache hits | App bug | Profile embedding or rerank tiers upstream of Redis |
| Only specific tiers miss | App bug | Inspect tier-specific TTLs and thresholds in [design doc](../CACHE_DEGRADATION.md) |

### Cache Smoke Validation

Use a canonical query twice (once with cleared cache, once immediately after):

1. **Cold run:** expect `bge-m3-encode-*`, `qdrant` retrieval, and `LLM` generation spans.
2. **Immediate replay:** on semantic cache hit, expect none of those spans for the same response path.

## Remediation

> **Caution:** Commands below mutate state. Run only after fast-path diagnosis
> confirms the issue is not an application bug.

### Redis Connection Refused

```bash
# 1. Check container status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps redis

# 2. Restart Redis
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart redis

# 3. Verify network reachability
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -h redis -a "$REDIS_PASSWORD" ping'
```

### Local REDIS_PASSWORD Drift

When bot preflight reports auth failures after a local `.env` change:

```bash
make local-redis-recreate
make test-bot-health
```

### Cache Corruption or Version Drift

If keys use an old `CACHE_VERSION` / `SEMANTIC_CACHE_VERSION`:

```bash
# Programmatic clear (uses SCAN, safe for large keyspaces)
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

Or via bot command: `/clearcache`

> **Avoid `KEYS *`** in production. `CacheLayerManager.clear_by_tier()` and
> `clear_semantic_cache()` use `SCAN` iteratively.

### Memory Issues

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" INFO memory' | grep used_memory_human
```

If near limit:
- Increase `maxmemory` in `compose.dev.yml` (dev) or host Redis config (production)
- Reduce exact-cache TTLs in `telegram_bot/integrations/cache.py` (`DEFAULT_TTLS`)
- Clear old entries via `clear_by_tier()`

## Impact on Users

When Redis is down, the system degrades gracefully:

- **Semantic cache unavailable** -- queries still work, no cache hits
- **Embeddings cache unavailable** -- fresh embeddings computed each time
- **Session history unavailable** -- new sessions lose context

Users still get responses, just without cache benefits.

## Prevention

- Monitor Redis memory via `redis-cli INFO memory`
- Set up alerting for `Redis connection refused` errors
- Regular cache health checks via `/stats` bot command
- Keep `compose.yml` and `compose.dev.yml` memory limits within host capacity

## Source Paths

| Component | Path |
|---|---|
| Cache implementation | [`telegram_bot/integrations/cache.py`](../../telegram_bot/integrations/cache.py) |
| Redis service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides | [`compose.dev.yml`](../../compose.dev.yml) |
| CI env fixture | [`tests/fixtures/compose.ci.env`](../../tests/fixtures/compose.ci.env) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs redis --tail=200` |
| Redis data volume | `redis_data` (inspect with `docker volume inspect dev_redis_data`) |
| Bot cache metrics | `/stats` command or Langfuse spans tagged `cache-semantic-check` |

## See Also

- [Qdrant Troubleshooting](QDRANT_TROUBLESHOOTING.md)
- [VPS Google Drive Ingestion Recovery](vps-gdrive-ingestion-recovery.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
