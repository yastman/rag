# Runbook: Telegram Bot Failure

> **Owner:** Bot & Pipeline team
> **Last verified:** 2026-05-12
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot
> ```

Use this runbook when **Telegram bot alerts fire** or the bot stops responding
to user messages. Covers container failures, error rate spikes, Telegram API
issues, query processing failures, slow responses, and memory pressure.

## Symptoms

- Bot not responding to Telegram messages
- High error rates in bot container logs
- Telegram API timeout or connection errors
- Queries returning errors or timing out
- Bot restarting repeatedly (crash loop)
- Slow responses (>5 s per query)
- Memory warnings or OOM kills in bot container

## Service / Container Map

| Compose service | Typical container names | Notes |
|---|---|---|
| `bot` | `dev-bot-1` (Compose v2+), `dev_bot_1` (legacy) | Main Telegram bot runtime (aiogram 3 + LangGraph pipeline) |
| `redis` | `dev-redis-1` | Cache layer (semantic cache, session, embeddings) |
| `qdrant` | `dev-qdrant-1` | Vector search backend |
| `litellm` | `dev-litellm-1` | LLM proxy (routes to upstream providers) |
| `bge-m3` | `dev-bge-m3-1` | Local embedding model server |

> The bot depends on `redis`, `qdrant`, `litellm`, and `bge-m3`. A failure in
> any upstream service can cascade into bot alerts.

## Fast-Path Diagnosis (read-only)

Run these commands before taking any remediation action.

### 1. Container status

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot
```

Check the `STATUS` column. A healthy bot shows `Up` with no restart counter.

### 2. Recent logs

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=200
```

Look for:
- `Starting bot` (indicates recent restart)
- `critical`, `fatal`, `panic` (critical errors)
- `telegram.*error`, `aiogram.*error` (API failures)
- `query.*error`, `retrieval.*error` (pipeline failures)
- `memory.*warning`, `oom` (memory pressure)

### 3. Upstream service health

```bash
# Redis
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" ping'

# Qdrant
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec qdrant sh -c 'wget -qO- http://localhost:6333/readyz'

# LiteLLM
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec litellm sh -c 'wget -qO- http://localhost:4000/health'
```

### 4. Resource usage

```bash
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep bot
```

---

## Alert: BotContainerDown

**Severity:** critical
**Condition:** No logs from `dev-bot` container for 5 minutes (fires after 2 m).

### Diagnosis

```bash
# Check if container exists and its state
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot

# Check Docker events for OOM or exit
docker events --filter container=dev-bot-1 --since 10m --until 0s 2>/dev/null | tail -20

# Inspect exit code of last run
docker inspect dev-bot-1 --format '{{.State.ExitCode}} {{.State.Error}}' 2>/dev/null
```

### Resolution

1. **Container exited cleanly (exit code 0):** May have been stopped manually. Restart:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d bot
   ```

2. **Container OOM-killed (exit code 137):** Increase memory limit in `compose.dev.yml` then restart:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d bot
   ```

3. **Container crash-looping (exit code 1):** Check logs for the root cause (missing env vars, dependency failure):
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=50
   ```
   Fix the underlying issue (missing `TELEGRAM_BOT_TOKEN`, unreachable Redis, etc.) and restart.

---

## Alert: BotHighErrorRate

**Severity:** warning
**Condition:** Error/exception/failed log rate > 0.1/s for 5 minutes.

### Diagnosis

```bash
# Count recent errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 10m 2>&1 | grep -icE '(error|exception|failed)'

# Identify top error patterns
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 10m 2>&1 | grep -iE '(error|exception|failed)' | sort | uniq -c | sort -rn | head -10
```

Common causes:
- Upstream service degradation (Redis, Qdrant, LiteLLM)
- Invalid or expired `TELEGRAM_BOT_TOKEN`
- Network partition between containers

### Resolution

1. **Upstream service issue:** Verify upstream health (see Fast-Path step 3). Restart the failing dependency.
2. **Token issue:** Verify `TELEGRAM_BOT_TOKEN` is set and valid. Recreate if expired.
3. **Transient spike:** If errors stop on their own and rate drops below threshold, the alert auto-resolves. Monitor for 10 minutes.

---

## Alert: BotCriticalError

**Severity:** critical
**Condition:** Any `critical`, `fatal`, or `panic` log line in the last 5 minutes.

### Diagnosis

```bash
# Find the critical error
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 10m 2>&1 | grep -iE '(critical|fatal|panic)'
```

### Resolution

1. **Unhandled exception / panic:** Capture the full traceback, file an issue, then restart:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bot
   ```

2. **Dependency initialization failure:** A critical error during startup usually means a required service is unreachable. Check upstream services and environment variables.

3. **Data corruption:** If the error references cache or graph state corruption, clear caches and restart:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "
   import asyncio, os
   from telegram_bot.integrations.cache import CacheLayerManager
   async def clear():
       cache = CacheLayerManager(redis_url=os.environ.get('REDIS_URL', 'redis://redis:6379'))
       await cache.initialize()
       print(await cache.clear_all_caches())
   asyncio.run(clear())
   "
   ```

---

## Alert: TelegramAPIError

**Severity:** warning
**Condition:** More than 5 Telegram/aiogram API errors in 5 minutes (fires after 3 m).

### Diagnosis

```bash
# Extract Telegram API errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 15m 2>&1 | grep -iE 'telegram.*error|aiogram.*error'
```

Common error types:
- `TelegramRetryAfter` -- rate limiting by Telegram servers
- `TelegramNetworkError` -- network connectivity to api.telegram.org
- `TelegramForbiddenError` -- bot was blocked by user (not actionable)
- `TelegramUnauthorizedError` -- invalid bot token

### Resolution

1. **Rate limiting (`RetryAfter`):** The bot automatically retries. If persistent, reduce message throughput or add delays between bulk sends.

2. **Network error:** Verify outbound connectivity from the bot container:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "import urllib.request; print(urllib.request.urlopen('https://api.telegram.org').status)"
   ```

3. **Unauthorized (401):** The bot token is invalid or revoked. Generate a new token via BotFather and update `TELEGRAM_BOT_TOKEN` in the environment, then restart.

4. **Forbidden errors (user blocked bot):** These are normal and not actionable. If they dominate the error count, consider filtering them from the alert rule.

---

## Alert: BotRestarted

**Severity:** info
**Condition:** More than one `Starting bot` log line in 5 minutes.

### Diagnosis

```bash
# Count recent restarts
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 30m 2>&1 | grep -c "Starting bot"

# Check restart policy and count
docker inspect dev-bot-1 --format '{{.RestartCount}}' 2>/dev/null
```

### Resolution

1. **Single restart after deploy:** Expected behavior. No action needed.

2. **Crash loop (multiple restarts in short window):** The bot is failing shortly after startup. Check logs immediately before each `Starting bot` line for the crash reason:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 30m 2>&1 | grep -B 20 "Starting bot" | tail -60
   ```

3. **OOM restarts:** Check if Docker is killing the container due to memory limits. See the BotMemoryWarning section below.

---

## Alert: QueryProcessingError

**Severity:** warning
**Condition:** More than 3 query/search/retrieval errors in 5 minutes (fires after 3 m).

### Diagnosis

```bash
# Find query processing errors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 10m 2>&1 | grep -iE 'query.*error|search.*failed|retrieval.*error'
```

Common causes:
- Qdrant collection missing or unhealthy
- BGE-M3 embedding service timeout
- LiteLLM proxy returning errors
- Graph node failure in LangGraph pipeline

### Resolution

1. **Qdrant issue:** Verify collection exists and is healthy:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec qdrant sh -c 'wget -qO- http://localhost:6333/collections'
   ```
   If the collection is missing, re-run ingestion. See [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md).

2. **Embedding service timeout:** Check BGE-M3 health and restart if needed:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bge-m3
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bge-m3
   ```

3. **LiteLLM errors:** Check the LLM proxy. See [LITEllm_FAILURE.md](LITEllm_FAILURE.md) for detailed diagnosis.

4. **Graph pipeline failure:** Inspect Langfuse traces for the failing query to identify which node failed. See [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) if traces are missing.

---

## Alert: SlowBotResponse

**Severity:** warning
**Condition:** More than 5 responses exceeding 5 s in 5 minutes.

### Diagnosis

```bash
# Find slow responses
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 10m 2>&1 | grep -iE 'response_time'

# Check upstream latency contributors
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bge-m3 --since 10m --tail=20
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs litellm --since 10m --tail=20
```

Typical latency contributors (in pipeline order):
1. Embedding generation (BGE-M3) -- normally 200-500 ms
2. Vector search (Qdrant) -- normally 50-200 ms
3. Reranking (ColBERT server-side) -- normally 100-300 ms
4. LLM generation (via LiteLLM) -- normally 1-3 s

### Resolution

1. **BGE-M3 slow:** The embedding model may be CPU-bound. Check resource usage and consider scaling or increasing `BGE_M3_TIMEOUT`.

2. **LLM generation slow:** Upstream provider latency. Check LiteLLM logs for timeout or retry patterns. Consider switching to a faster model or reducing `GENERATE_MAX_TOKENS`.

3. **Qdrant slow:** Large collection scan or resource contention. See [QDRANT_TROUBLESHOOTING.md](QDRANT_TROUBLESHOOTING.md).

4. **Cache miss storm:** If the semantic cache is cold (after a restart or clear), initial queries will be slow. This self-resolves as the cache warms. See [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md).

---

## Alert: BotMemoryWarning

**Severity:** warning
**Condition:** Any memory warning or OOM log line in the last 5 minutes.

### Diagnosis

```bash
# Check current memory usage
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}" | grep bot

# Check for memory warnings in logs
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --since 30m 2>&1 | grep -iE 'memory.*warning|memory.*high|oom'

# Check container memory limit
docker inspect dev-bot-1 --format '{{.HostConfig.Memory}}' 2>/dev/null
```

### Resolution

1. **Memory approaching limit:** Increase the memory limit in `compose.dev.yml` (dev) or `compose.vps.yml` (production):
   ```yaml
   bot:
     deploy:
       resources:
         limits:
           memory: 2G  # increase from default
   ```
   Then recreate:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d bot
   ```

2. **Memory leak suspicion:** If memory grows continuously without stabilizing, restart the bot as a short-term fix and file an issue with memory profiling data:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bot
   ```

3. **OOM kill confirmed:** Docker killed the process. Check `docker events` for the OOM event, increase memory limits, and restart.

---

## Impact on Users

When the bot is down or degraded:

- **Container down:** Users receive no responses until the bot restarts.
- **High error rate:** Some queries fail; users may see error messages or no response.
- **Telegram API errors:** Messages may not be delivered or acknowledged.
- **Query processing errors:** Users receive fallback error messages instead of answers.
- **Slow responses:** Users experience long waits (>5 s) before receiving answers.
- **Memory issues:** Bot may become unresponsive or crash, causing temporary downtime.

The bot's `restart: unless-stopped` policy in Compose provides automatic recovery for transient crashes.

## Prevention

- Monitor bot container with `docker stats` or Prometheus metrics
- Set up Langfuse alerts for pipeline latency regression
- Keep memory limits aligned with actual usage (headroom of at least 30%)
- Review error logs weekly for recurring patterns
- Validate environment variables before deployments using bot preflight checks
- Use the `/stats` bot command to check runtime health

## Source Paths

| Component | Path |
|---|---|
| Bot entry point | [`telegram_bot/bot.py`](../../telegram_bot/bot.py) |
| Bot Dockerfile | [`telegram_bot/Dockerfile`](../../telegram_bot/Dockerfile) |
| Bot service definition | [`compose.yml`](../../compose.yml) |
| Dev overrides | [`compose.dev.yml`](../../compose.dev.yml) |
| VPS overrides | [`compose.vps.yml`](../../compose.vps.yml) |
| Alert rules | [`docker/monitoring/rules/telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| Cache integration | [`telegram_bot/integrations/cache.py`](../../telegram_bot/integrations/cache.py) |

## See Also

- [REDIS_CACHE_DEGRADATION.md](REDIS_CACHE_DEGRADATION.md) -- cache service issues
- [QDRANT_TROUBLESHOOTING.md](QDRANT_TROUBLESHOOTING.md) -- vector DB issues
- [LITEllm_FAILURE.md](LITEllm_FAILURE.md) -- LLM proxy issues
- [LANGFUSE_TRACING_GAPS.md](LANGFUSE_TRACING_GAPS.md) -- observability gaps
- [vps-gdrive-ingestion-recovery.md](vps-gdrive-ingestion-recovery.md) -- ingestion pipeline
- [Bot Architecture](../BOT_ARCHITECTURE.md) -- bot design overview
- [Bot Internal Structure](../BOT_INTERNAL_STRUCTURE.md) -- code navigation
