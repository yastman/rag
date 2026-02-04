---
paths: "docker/**/*.*, docker-compose*.yml, **/monitoring/**"
---

# Docker & Infrastructure

## Full Stack (16 containers)

| Container | Port | Purpose |
|-----------|------|---------|
| dev-bot | - | Telegram bot (healthy) |
| dev-litellm | 4000 | LLM Gateway proxy |
| dev-langfuse | 3001 | LLM observability UI |
| dev-langfuse-worker | 3030 | Langfuse background jobs |
| dev-redis | 6379 | App cache (semantic, rerank, sparse) |
| dev-redis-langfuse | 6380 | Langfuse queues (separate) |
| dev-qdrant | 6333 | Vector database |
| dev-postgres | 5432 | Langfuse metadata storage |
| dev-clickhouse | 8123, 9009 | Langfuse analytics |
| dev-minio | 9090, 9091 | Langfuse S3 storage |
| dev-mlflow | 5000 | Experiment tracking |
| dev-user-base | 8003 | Russian embeddings (deepvk/USER-base) |
| dev-bge-m3 | 8000 | BGE-M3 dense+sparse embeddings |
| dev-bm42 | 8002 | BM42 sparse embeddings (FastEmbed) |
| dev-docling | 5001 | Document parsing (PDF/DOCX/CSV) |
| dev-lightrag | 9621 | LightRAG graph-based retrieval |

## Docker Profiles (Fast Startup)

| Command | Services | Use Case |
|---------|----------|----------|
| `make docker-core-up` | postgres, qdrant, redis, docling, bm42 | Daily ingestion dev |
| `make docker-bot-up` | core + litellm, bot | Bot development |
| `make docker-obs-up` | core + loki, promtail, alertmanager | Debug logging |
| `make docker-ml-up` | core + langfuse stack, mlflow | ML experiments |
| `make docker-ai-up` | core + bge-m3, user-base, lightrag | Heavy AI models |
| `make docker-ingest-up` | core + ingestion | Ingestion container |
| `make docker-full-up` | everything (16+ services) | Full stack |

### Combining Profiles

```bash
# Bot + observability
docker compose -f docker-compose.dev.yml --profile bot --profile obs up -d

# Using COMPOSE_PROFILES env var
COMPOSE_PROFILES=bot,obs docker compose -f docker-compose.dev.yml up -d
```

### Startup Times (warm images)

| Profile | Services | Target Time |
|---------|----------|-------------|
| core | 5 | ≤90s |
| bot | 7 | ≤2-3 min |
| full | 16+ | ≤5 min |

## LLM Gateway (LiteLLM)

```
Bot → LiteLLM Proxy (:4000) → Cerebras/Groq/OpenAI → Langfuse tracing
```

**Config:** `docker/litellm/config.yaml`

| Model | Provider | Purpose |
|-------|----------|---------|
| `gpt-4o-mini` | Cerebras (zai-glm-4.7) | Primary model |
| `gpt-4o-mini-fallback` | Groq (llama-3.1-70b) | Fallback 1 |
| `gpt-4o-mini-openai` | OpenAI (gpt-4o-mini) | Fallback 2 |

## Telegram Bot (Docker)

```bash
# Start full dev stack (Qdrant, Redis, Langfuse, MLflow, bot)
docker compose -f docker-compose.dev.yml up -d

# Build and restart bot only
docker compose -f docker-compose.dev.yml build bot
docker compose -f docker-compose.dev.yml up -d bot

# Check bot logs
docker logs dev-bot -f

# Verify bot health
docker ps --format "table {{.Names}}\t{{.Status}}" | grep bot
```

Bot connects to: `@test_nika_homes_bot` (configured via `TELEGRAM_BOT_TOKEN`)

Bot responses use Markdown formatting (`parse_mode="Markdown"`).

## Monitoring & Alerting

```bash
make monitoring-up          # Start Loki, Promtail, Alertmanager
make monitoring-down        # Stop monitoring stack
make monitoring-status      # Check health
make monitoring-test-alert  # Send test alert to Telegram
make monitoring-logs        # View logs
```

| Container | Port | Purpose |
|-----------|------|---------|
| dev-loki | 3100 | Log aggregation |
| dev-promtail | - | Log collection from Docker |
| dev-alertmanager | 9093 | Alert routing to Telegram |

**Config:** `docker/monitoring/` (loki.yaml, promtail.yaml, alertmanager.yaml, rules/)

**Env vars:** `TELEGRAM_ALERTING_BOT_TOKEN`, `TELEGRAM_ALERTING_CHAT_ID`

**Docs:** `docs/ALERTING.md`

## Parallel Claude Workers

Запуск нескольких Claude-агентов для параллельной работы над независимыми задачами.

**Документация:** [docs/PARALLEL-WORKERS.md](docs/PARALLEL-WORKERS.md)

**Короткий синтаксис (из Claude):**
```
/parallel docs/plans/2026-01-28-feature.md
W1: 1,2,5
W2: 3,4
```

Claude понимает: прочитать план, запустить `spawn-claude` для каждого воркера с правильными скиллами. Оркестратор (основной Claude) не делает задачи сам — только коммитит после воркеров.

**Правило:** 1 воркер = 1 набор независимых файлов. Никогда не делить один файл между воркерами.

## Docker Hardening (Feb 2026)

**Phase 1 — Critical fixes:**

| Issue | Fix |
|-------|-----|
| ENTRYPOINT + command duplication | Removed duplicate command from ingestion |
| Healthchecks using `requests` | Switched to `urllib.request` (stdlib) |
| Ports open to LAN | Bound langfuse/litellm to `127.0.0.1` |
| Floating image tags | Pinned minio, docling by digest/release |

**Phase 2 — Operational hygiene:**

| Feature | Implementation |
|---------|---------------|
| Memory limits | `--compatibility` flag via `COMPOSE_CMD` in Makefile |
| Log rotation | `50m/5` for bot, litellm, langfuse, langfuse-worker |
| Fail-fast secrets | `${VAR:?VAR is required}` syntax for critical env vars |
| Image policy | Versioned tags OK, digest only for floating (documented in DOCKER.md) |

**Required env vars by profile:**

| Profile | Required |
|---------|----------|
| core | None (dev defaults) |
| bot | `TELEGRAM_BOT_TOKEN`, `VOYAGE_API_KEY`, `LITELLM_MASTER_KEY` + 1 LLM provider |
| ml | `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` |

**Verification:**
```bash
docker compose --compatibility -f docker-compose.dev.yml config --quiet
docker inspect dev-bm42 --format '{{.HostConfig.Memory}}'  # != 0
docker inspect dev-litellm --format '{{json .HostConfig.LogConfig}}'  # max-size: 50m
TELEGRAM_BOT_TOKEN= make docker-bot-up  # Must fail with "is required"
```

**Plan:** `docs/plans/2026-02-04-docker-hardening.md`

## Loki Rules Mount (Feb 2026)

**Issue:** Loki Ruler expects rules in `/etc/loki/rules/<tenant>/` (tenant=`fake` in dev), but rules were mounted to `/etc/loki/rules/`.

**Fix:** Changed mount in `docker-compose.dev.yml`:
```yaml
# Before (broken)
- ./docker/monitoring/rules:/etc/loki/rules:ro
# After (working)
- ./docker/monitoring/rules:/etc/loki/rules/fake:ro
```

**Verification:**
```bash
curl -sS http://localhost:3100/loki/api/v1/rules | head -5  # Should return YAML, not 400
```

**Plan:** `docs/plans/2026-02-04-alerting-telegram-audit-and-fix-spec.md`
