# Runbook: Telegram Bot Failure

> **Owner:** Bot core / On-call
> **Last verified:** 2026-05-22
> **Verification command:**
> ```bash
> COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot
> ```

Use this runbook when alerts from `docker/monitoring/rules/telegram-bot.yaml` fire or the bot is misbehaving end-to-end.

## Covered Alerts

| Alert | Severity | Source |
|---|---|---|
| `BotContainerDown` | critical | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `BotHighErrorRate` | warning | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `BotCriticalError` | critical | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `TelegramAPIError` | warning | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `BotRestarted` | info | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `QueryProcessingError` | warning | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `SlowBotResponse` | warning | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |
| `BotMemoryWarning` | warning | [`telegram-bot.yaml`](../../docker/monitoring/rules/telegram-bot.yaml) |

## Service / Container Map

| Compose service | Typical container names |
|---|---|
| `bot` | `dev-bot-1`, `dev_bot_1` |

> Service endpoints, ports, and Compose profiles: [`DOCKER.md`](../../DOCKER.md).
> Local dev workflow: [`docs/LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md).

## Fast-Path Diagnosis (read-only)

### 1. Container state

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml ps bot
docker inspect dev-bot-1 --format '
  Name={{.Name}}
  Status={{.State.Status}}
  Restarts={{.RestartCount}}
  OOMKilled={{.State.OOMKilled}}
  ExitCode={{.State.ExitCode}}
'
```

If `Status` is `restarting` and `RestartCount` keeps climbing, treat as `BotContainerDown`/`BotRestarted` and continue with logs.

### 2. Bounded log slice

```bash
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml logs bot --tail=200
```

Look for the same patterns that drive the alerts:

| Pattern | Likely alert |
|---|---|
| `error`, `exception`, `failed` (rate based) | `BotHighErrorRate` |
| `critical`, `fatal`, `panic` | `BotCriticalError` |
| `telegram.*error`, `aiogram.*error` | `TelegramAPIError` |
| `Starting bot` (more than once in 5m) | `BotRestarted` |
| `query.*error`, `search.*failed`, `retrieval.*error` | `QueryProcessingError` |
| `response_time.*5000` (or higher) | `SlowBotResponse` |
| `memory.*warning`, `memory.*high`, `oom` | `BotMemoryWarning` |

### 3. Health checks for the bot's hard dependencies

If the bot is up but failing every query, the root cause is usually one of its dependencies:

```bash
# Qdrant
curl -fsS http://localhost:6333/readyz

# Redis (app cache)
COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml exec redis sh -lc 'redis-cli -a "$REDIS_PASSWORD" ping'

# LiteLLM
curl -fsS http://localhost:4000/health/liveliness
```

Fan-out to the dedicated runbook for whichever check fails: [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md), [`REDIS_CACHE_DEGRADATION.md`](REDIS_CACHE_DEGRADATION.md), [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md).

### 4. Trace freshness

```bash
make validate-traces-fast
```

If traces are stale or missing, see [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md). Langfuse can be healthy while the bot still records `LLM failed: Connection error` spans — that points back at LiteLLM, not Langfuse.

## Service Failure vs App Bug

| Observation | Interpretation | Next step |
|---|---|---|
| Container `Exited (137)` or `OOMKilled=true` | Service failure (memory) | Increase memory limit in `compose.dev.yml`; investigate workload |
| Container `Exited (127)` with bind-mount error in `inspect` | Stale Docker Desktop / WSL bind-mount | Recreate only the bot: `docker compose up -d --force-recreate bot` |
| `RestartCount` climbing, no log entries | Service failure (startup crash) | `docker compose logs bot --since=10m` and inspect `compose.yml` env contract |
| Bot is up, alerts only show `TelegramAPIError` | App bug or upstream Telegram outage | Verify `TELEGRAM_BOT_TOKEN` is present (do not print it); check `https://api.telegram.org` reachability |
| `BotHighErrorRate` with no critical errors | App bug or load spike | Profile slow node from Langfuse; check rate limits |
| `QueryProcessingError` correlated with Qdrant warnings | Service failure (Qdrant) | [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md) |
| `SlowBotResponse` only on cache miss | App bug / capacity | Check Redis hit rate; consider preheating |
| `BotMemoryWarning` rising over hours | Memory leak | Capture `docker stats bot`; restart and compare |

## Source Paths

| Component | Path |
|---|---|
| Bot entry point | [`telegram_bot/bot.py`](../../telegram_bot/bot.py) |
| LangGraph wiring | [`telegram_bot/graph/`](../../telegram_bot/graph/) |
| Score taxonomy | [`telegram_bot/scoring.py`](../../telegram_bot/scoring.py), [`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md) |
| Compose service definition | [`compose.yml`](../../compose.yml), [`compose.dev.yml`](../../compose.dev.yml) |

## Logs and Artifacts

| Artifact | Location / command |
|---|---|
| Runtime logs | `docker compose logs bot --tail=200` |
| Health probe | `make test-bot-health` |
| Langfuse traces | Langfuse UI → filter by `service=bot`; or `make validate-traces-fast` |
| Container metadata | `docker inspect dev-bot-1` |

## Remediation

> ⚠️ **Caution:** Mutating commands. Run only after fast-path diagnosis confirms the issue.

### `BotContainerDown`

1. Inspect exit reason (see Fast-Path Diagnosis #1).
2. If `OOMKilled=true`: raise `services.bot.deploy.resources.limits.memory` in `compose.dev.yml` and recreate.
3. If startup crash: fix the surfaced error, then:
   ```bash
   COMPOSE_PROJECT_NAME=dev docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml up -d --force-recreate bot
   ```

### `BotHighErrorRate` / `BotCriticalError` / `QueryProcessingError`

1. Capture the offending stack trace from logs.
2. Cross-reference with current Langfuse traces.
3. If a dependency is the culprit, follow that runbook; do not preemptively restart the bot.

### `TelegramAPIError`

1. Confirm `TELEGRAM_BOT_TOKEN` env var is present (presence only, never print).
2. Check Telegram BotFather status / public Telegram outage page.
3. If the bot is rate-limited (429), back off retries; do not loop.

### `BotRestarted`

`info`-severity. Confirm the cause: planned deploy, OOM, or crash loop. Treat repeated restarts as `BotContainerDown`.

### `SlowBotResponse`

1. Compare current p50/p95 from Langfuse with baseline.
2. Check upstream latency (LiteLLM, Qdrant, BGE-M3).
3. If only cold cache: warm semantic + search caches with synthetic queries.

### `BotMemoryWarning`

1. `docker stats dev-bot-1` for current RSS.
2. If steady growth: capture heap snapshot via tracemalloc / py-spy attach, then restart.
3. If transient spike: raise the dev memory limit, file a follow-up to investigate.

## Prevention

- Keep Compose memory limits headroom ≥ 30%.
- Wire `make pre-push` and `make check` into the local loop.
- Watch the `bge_embed_error`, `llm_timeout`, and `safe_fallback_used` Langfuse scores — they typically rise before `BotHighErrorRate` fires.
- Capture restart events in CHANGELOG when caused by deploys.

## See Also

- [`LITEllm_FAILURE.md`](LITEllm_FAILURE.md)
- [`REDIS_CACHE_DEGRADATION.md`](REDIS_CACHE_DEGRADATION.md)
- [`QDRANT_TROUBLESHOOTING.md`](QDRANT_TROUBLESHOOTING.md)
- [`LANGFUSE_TRACING_GAPS.md`](LANGFUSE_TRACING_GAPS.md)
- [`EMBEDDING_SERVICE_FAILURE.md`](EMBEDDING_SERVICE_FAILURE.md)
- [`docs/RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md)
- [`DOCKER.md`](../../DOCKER.md)
