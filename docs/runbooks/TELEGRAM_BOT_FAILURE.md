# Runbook: Telegram Bot Failure

> **Related docs:**
> - [Bot Architecture](../BOT_ARCHITECTURE.md) -- high-level design of the Telegram bot
> - [Bot Internal Structure](../BOT_INTERNAL_STRUCTURE.md) -- module layout and data flow
> - [Local Development Guide](../LOCAL-DEVELOPMENT.md) -- running the bot locally

> **Owner:** Telegram Bot subsystem
> **Last verified:** 2026-05-12
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot pgrep -f 'telegram_bot.main'
> ```

Use this runbook when **Telegram bot alerts fire** or the bot service is
unresponsive. Covers container health, error rates, Telegram API issues, query
processing failures, slow responses, and memory pressure.

## Symptoms

- Bot not responding to user messages
- High error rate in bot logs
- Critical or fatal errors in log output
- Telegram API returning errors (rate limits, network issues)
- Bot restarting repeatedly (crash loop)
- Query/search operations failing
- Responses taking longer than 5 seconds
- Memory warnings or OOM events

## Service / Container Map

| Compose service | Typical container names | Notes |
|---|---|---|
| `bot` | `dev-bot-1` (Compose v2+), `dev_bot_1` (legacy) | Main Telegram bot process (`telegram_bot.main`) |
| `redis` | `dev-redis-1` | Semantic cache and session storage |
| `qdrant` | `dev-qdrant-1` | Vector search for document retrieval |
| `bge-m3` | `dev-bge-m3-1` | Dense/sparse embedding service |
| `user-base` | `dev-user-base-1` | User embedding service for semantic cache |
| `litellm` | `dev-litellm-1` | LLM proxy gateway |
| `postgres` | `dev-postgres-1` | Real estate database |

> The bot depends on all of the above services (declared via `depends_on` with
> `service_healthy` conditions in [`compose.yml`](../../compose.yml)).
> A failure in any dependency can cascade into bot errors.

## Fast-Path Diagnosis (read-only)

Run these commands before deciding whether the issue is a service failure or an
application bug.

### 1. Container health and process

```bash
# Check bot container status
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot

# Verify bot process is running
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot pgrep -f 'telegram_bot.main'
```

Expected: container status `Up (healthy)` and a PID returned by `pgrep`.
If no process is found, the bot has crashed or failed to start.

### 2. Recent logs

```bash
# Last 200 lines from bot container
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=200

# Filter for errors only
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=500 | grep -i "error\|exception\|critical\|fatal"
```

Look for:
- `TelegramUnauthorizedError` -- invalid bot token
- `TelegramConflictError` -- another polling instance running
- `TelegramNetworkError` -- network connectivity issue
- `TelegramRetryAfter` -- rate limited by Telegram API
- `redis.*error` -- cache connection failures
- `query.*error` or `retrieval.*error` -- RAG pipeline failures

### 3. Dependency health

```bash
# Check all bot dependencies in one pass
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps redis qdrant bge-m3 user-base litellm postgres
```

If any dependency shows `unhealthy` or `Exit`, that is likely the root cause.

### 4. Memory usage

```bash
# Check container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep bot
```

The bot container has a memory limit of **512M** (set in `compose.yml`).
If usage is near that limit, memory pressure may cause OOM kills.

### 5. Restart count

```bash
# Check if container has been restarting
docker inspect --format='{{.RestartCount}}' dev-bot-1
```

A high restart count indicates a crash loop.

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| Bot container not running / exited | Service failure | Check logs for crash reason, restart |
| Bot running but not responding | App bug or Telegram API issue | Check for `TelegramConflictError` (duplicate polling) |
| `TelegramUnauthorizedError` in logs | Invalid token | Verify `TELEGRAM_BOT_TOKEN` in `.env` |
| `TelegramConflictError` in logs | Duplicate bot instance | Stop other instances, check polling lock |
| `TelegramRetryAfter` in logs | Rate limited | Wait for cooldown, reduce message frequency |
| `TelegramNetworkError` in logs | Network issue | Check DNS, outbound connectivity |
| Redis/Qdrant errors in bot logs | Dependency failure | See [Redis runbook](REDIS_CACHE_DEGRADATION.md) or [Qdrant runbook](QDRANT_TROUBLESHOOTING.md) |
| LLM/LiteLLM errors in bot logs | LLM proxy failure | See [LiteLLM runbook](LITEllm_FAILURE.md) |
| High memory, OOM messages | Resource exhaustion | Increase memory limit or investigate leak |
| Slow responses (>5s) | Performance degradation | Profile embedding/retrieval/generation stages |
| Query processing errors | RAG pipeline issue | Check bge-m3, qdrant, litellm connectivity |

## Remediation

> **Caution:** Commands below mutate state. Run only after fast-path diagnosis
> confirms the issue type.

### BotContainerDown -- Container not running

```bash
# 1. Check why the container stopped
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=50

# 2. Restart the bot
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d bot

# 3. Verify it comes up healthy
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot
```

If the bot fails to start due to missing dependencies, bring up all services:

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d
```

### BotHighErrorRate / BotCriticalError -- Error storms

```bash
# 1. Identify the error pattern
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=500 | grep -i "error\|critical" | sort | uniq -c | sort -rn | head -20

# 2. If errors relate to a dependency, restart that dependency first
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart redis qdrant bge-m3

# 3. Then restart the bot
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bot
```

### TelegramAPIError -- Telegram API communication failures

```bash
# 1. Check if this is a rate limit issue
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=200 | grep -i "retryafter\|429\|flood"

# 2. Check outbound network connectivity
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "import urllib.request; print(urllib.request.urlopen('https://api.telegram.org', timeout=10).status)"

# 3. Verify bot token is valid
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "
import os, urllib.request, json
token = os.environ['TELEGRAM_BOT_TOKEN']
resp = urllib.request.urlopen(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
print(json.loads(resp.read()))
"
```

If rate limited, the bot uses `tenacity` retry with exponential backoff. Wait
for the cooldown period before manual intervention.

### BotRestarted -- Crash loop detection

```bash
# 1. Check restart count and timing
docker inspect --format='{{.RestartCount}} restarts, last at {{.State.StartedAt}}' dev-bot-1

# 2. Check for polling lock conflicts
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=100 | grep -i "conflict\|polling.*lock\|PollingLockBusy"

# 3. If polling lock is stale, clear it via Redis
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" DEL bot:polling_lock'

# 4. Restart bot cleanly
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bot
```

### QueryProcessingError -- RAG pipeline failures

```bash
# 1. Identify which stage is failing
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=300 | grep -i "query\|retrieval\|search\|embedding"

# 2. Test embedding service directly
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "
import urllib.request
resp = urllib.request.urlopen('http://bge-m3:8000/health', timeout=10)
print('bge-m3:', resp.status)
"

# 3. Test vector DB
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "
import urllib.request
resp = urllib.request.urlopen('http://qdrant:6333/readyz', timeout=10)
print('qdrant:', resp.status)
"

# 4. Test LLM proxy
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec bot python -c "
import urllib.request
resp = urllib.request.urlopen('http://litellm:4000/health/liveliness', timeout=10)
print('litellm:', resp.status)
"
```

### SlowBotResponse -- Performance degradation

```bash
# 1. Check which stage is slow via Langfuse traces
# Look for spans with high duration: bge-m3-encode, qdrant-search, llm-generate

# 2. Check embedding service latency
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bge-m3 --tail=50

# 3. Check Redis latency (cache misses cause full pipeline runs)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" --latency-history -i 5'

# 4. If bge-m3 is overloaded, check its memory and CPU
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -E "bot|bge-m3|qdrant|litellm"
```

Common causes:
- bge-m3 cold start (first request after container start takes longer)
- Qdrant collection not indexed (check `HNSW` segment status)
- LLM provider latency (check LiteLLM logs)
- Redis cache miss storm after cache flush

### BotMemoryWarning -- Memory pressure

```bash
# 1. Check current memory usage
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}" | grep bot

# 2. If near 512M limit, restart to reclaim memory
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml restart bot

# 3. For persistent memory growth, check for leaks
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=500 | grep -i "memory\|oom\|killed"
```

If memory issues persist after restart:
- Increase the memory limit in `compose.yml` or `compose.dev.yml`
- Check for unbounded caches or session accumulation
- Review `deploy.resources.limits.memory` (currently `512M`)

## Impact on Users

When the bot is down or degraded:

| Scenario | User impact |
|---|---|
| Bot container down | No responses at all; messages queue in Telegram servers |
| High error rate | Intermittent failures; some queries return error messages |
| Telegram API errors | Bot cannot send replies; messages are lost |
| Query processing errors | Users get fallback error messages instead of RAG answers |
| Slow responses | Users wait >5s; may retry and create duplicate load |
| Memory pressure | Degraded performance leading to eventual OOM and restart |

Telegram queues undelivered updates for up to 24 hours. Once the bot recovers,
it processes pending messages automatically (unless the offset has advanced).

## Prevention

- Monitor bot container health via the `BotContainerDown` alert (fires after 2m of no logs)
- Set up the full observability stack (`obs` profile) for Loki-based log alerting
- Use `/stats` bot command to check runtime health metrics
- Keep `TELEGRAM_BOT_TOKEN` rotation coordinated with deploys
- Run preflight checks on startup (handled automatically by `telegram_bot.preflight`)
- Review Langfuse traces periodically for latency regressions
- Ensure `BOT_START_MAX_ATTEMPTS` (default 10) and retry delays are tuned for your environment

## Source Paths

| Component | Path |
|---|---|
| Bot entry point | [`telegram_bot/main.py`](../../telegram_bot/main.py) |
| Bot application | [`telegram_bot/bot.py`](../../telegram_bot/bot.py) |
| Preflight checks | [`telegram_bot/preflight.py`](../../telegram_bot/preflight.py) |
| Polling lock | [`telegram_bot/integrations/polling_lock.py`](../../telegram_bot/integrations/polling_lock.py) |
| Cache integration | [`telegram_bot/integrations/cache.py`](../../telegram_bot/integrations/cache.py) |
| Bot Dockerfile | [`telegram_bot/Dockerfile`](../../telegram_bot/Dockerfile) |
| Compose service | [`compose.yml`](../../compose.yml) |
| Alert rules | [`docker/monitoring/rules/telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| Alertmanager config | [`docker/monitoring/alertmanager.yaml`](../../docker/monitoring/alertmanager.yaml) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Bot runtime logs | `docker compose logs bot --tail=200` |
| Structured log file | `logs/bot-run.log` (inside container, if file handler configured) |
| Langfuse traces | Langfuse UI, service name `telegram-bot` |
| Prometheus alerts | Loki alert rules in `docker/monitoring/rules/telegram-bot.yaml` |
| Container inspect | `docker inspect dev-bot-1` |

## See Also

- [Redis Cache Degradation](REDIS_CACHE_DEGRADATION.md)
- [Qdrant Troubleshooting](QDRANT_TROUBLESHOOTING.md)
- [LiteLLM Failure](LITEllm_FAILURE.md)
- [Langfuse Tracing Gaps](LANGFUSE_TRACING_GAPS.md)
- [Docker Services Reference](../../DOCKER.md)
- [Local Development Guide](../LOCAL-DEVELOPMENT.md)
