---
paths: "docker/**/*.*, docker-compose*.yml, **/monitoring/**"
---

# Docker & Infrastructure

## Full Stack (14 containers)

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
| dev-user-base | 8003 | Russian embeddings (deepvk/USER2-base) |
| dev-bge-m3 | 8000 | BGE-M3 dense+sparse embeddings |
| dev-docling | 5001 | Document parsing (PDF/DOCX/CSV) |

## Docker Profiles (Fast Startup)

| Command | Services | Use Case |
|---------|----------|----------|
| `make docker-core-up` | postgres, qdrant, redis, docling | Daily ingestion dev |
| `make docker-bot-up` | core + litellm, bot | Bot development |
| `make docker-obs-up` | core + loki, promtail, alertmanager | Debug logging |
| `make docker-ml-up` | core + langfuse stack, mlflow | ML experiments |
| `make docker-ai-up` | core + bge-m3, user-base | Heavy AI models |
| `make docker-eval-up` | core + mlflow | Evaluation (RAGAS, A/B tests) |
| `make docker-ingest-up` | core + ingestion | Ingestion container |
| `make docker-voice-up` | core + livekit, sip, voice-agent | Voice/SIP dev (preflight check) |
| `make docker-full-up` | everything (14+ services) | Full stack |

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

## VPS Stack (Local Embeddings)

**VPS:** `admin@95.111.252.29:1654` | Alias: `ssh vps` | Path: `/opt/rag-fresh`

```bash
# Start all services
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"

# With ingestion profile
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d"
```

| Service | Purpose | Memory |
|---------|---------|--------|
| postgres | CocoIndex state | 512MB |
| redis | Cache (semantic, rerank, sparse) | 300MB |
| qdrant | Vector DB | 1GB |
| docling | Document parsing | 2GB |
| bge-m3 | Dense embeddings + ColBERT rerank | 4GB |
| user-base | Semantic cache (USER2-base) | 2GB |
| litellm | LLM gateway | 512MB |
| bot | Telegram bot | 512MB |
| ingestion | CocoIndex pipeline (profile: ingest) | 512MB |

**Feature flags:**
```bash
RETRIEVAL_DENSE_PROVIDER=bge_m3_api  # bge_m3_api | voyage
RERANK_PROVIDER=colbert              # colbert | none | voyage
BGE_M3_URL=http://bge-m3:8000
```

**Collection:** `gdrive_documents_bge` (1024-dim BGE-M3 dense + BGE-M3 sparse, field name "bm42" kept)

### VPS Code Deployment (Hot Reload)

Volume mounts позволяют обновлять код без rebuild:

```yaml
# docker-compose.vps.yml (ingestion service)
volumes:
  - ./src:/app/src:ro
  - ./telegram_bot:/app/telegram_bot:ro
```

**Workflow:**
```bash
# 1. Sync code
rsync -avz src/ vps:/opt/rag-fresh/src/

# 2. Restart (НЕ rebuild)
ssh vps "docker restart vps-ingestion"
# Готово за 5 секунд
```

**ВАЖНО:** Volume mounts применяются только при создании контейнера. После изменения compose:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml --profile ingest up -d --force-recreate ingestion"
```

### VPS Quick Commands

```bash
# Статус
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"

# Логи
ssh vps "docker logs vps-bot --tail 50"
ssh vps "docker logs vps-ingestion --tail 50"

# Restart сервиса
ssh vps "docker restart vps-bot"

# Память
ssh vps "docker stats --no-stream | grep vps"

# Диск
ssh vps "docker system df"
ssh vps "df -h /"

# Очистка (осторожно!)
ssh vps "docker builder prune -f"           # Build cache
ssh vps "docker image prune -f"             # Dangling images
# НИКОГДА: docker system prune --volumes    # Удалит данные!
```

### VPS Troubleshooting

| Проблема | Решение |
|----------|---------|
| Volume mounts не работают | `--force-recreate` один раз |
| `No space left on device` | `docker builder prune -a -f` |
| Image 28GB (ingestion) | `RUN chown -R` дублирует слой → использовать `COPY --chown` |
| Код не обновился | Проверить mounts: `docker inspect vps-ingestion --format '{{json .Mounts}}'` |
| Container unhealthy | `docker logs vps-{service} --tail 50` |

### VPS Heavy Commands (tmux pattern)

Для тяжёлых команд (docker build, etc) — создать tmux window:

```bash
# 1. Создать окно
tmux new-window -n "W-VPS"

# 2. SSH
tmux send-keys -t "W-VPS" 'ssh vps' Enter

# 3. Команда (после паузы)
sleep 2 && tmux send-keys -t "W-VPS" 'cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml build 2>&1 | tee logs/build.log; echo "[COMPLETE]"' Enter
```

Пользователь видит вывод в tmux, Claude ждёт feedback.

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

## Building Images (Docker Bake)

```bash
# Build all 5 custom images in parallel
docker buildx bake --load

# Build a single target
docker buildx bake bot
```

`docker-bake.hcl` defines targets: `bot`, `bge-m3`, `user-base`, `ingestion`, `docling`.

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

**Bot Langfuse env vars** (docker-compose.dev.yml):
```yaml
LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-}   # optional, empty disables tracing
LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-}
LANGFUSE_HOST: http://langfuse:3000
```

Graceful degradation: tracing disabled when keys are empty (via `observability.py`).

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
| bot | `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY` + 1 LLM provider (dev also needs `VOYAGE_API_KEY`) | CRM (optional): `KOMMO_LEAD_SCORE_FIELD_ID`, `KOMMO_LEAD_BAND_FIELD_ID`, `NURTURING_ENABLED`, `NURTURING_INTERVAL_MINUTES`, `FUNNEL_ROLLUP_CRON` |
| ml | `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` |

**Verification:**
```bash
docker compose --compatibility -f docker-compose.dev.yml config --quiet
docker inspect dev-bge-m3 --format '{{.HostConfig.Memory}}'  # != 0
docker inspect dev-litellm --format '{{json .HostConfig.LogConfig}}'  # max-size: 50m
TELEGRAM_BOT_TOKEN= make docker-bot-up  # Must fail with "is required"
```

**Plan:** `docs/plans/2026-02-04-docker-hardening.md`

**Phase 3 — UV Migration (Feb 2026):**

| Service | Change |
|---------|--------|
| Bot | `uv pip install -r requirements.txt` → `uv sync --frozen --no-dev` + `pyproject.toml` |
| BGE-M3 | `uv pip install -r requirements.txt` → `uv sync --frozen --no-dev` + `uv.lock` |
| USER-base | `uv pip install -r requirements.txt` → `uv sync --frozen --no-dev` + `pyproject.toml` |
| Ingestion | uv 0.5.18 → uv 0.10 pin |
| Healthchecks | `curl -f` → `python urllib.request` (compose files) |

**Docker pattern (all custom services):**
```dockerfile
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
RUN uv sync --frozen --no-dev --no-install-project  # deps layer
COPY . .
RUN uv sync --frozen --no-dev                        # code layer
FROM python:3.12-slim-bookworm AS runtime
COPY --from=builder /app/.venv /app/.venv
```

**Plan:** `docs/plans/2026-02-08-uv-docker-migration.md`

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
