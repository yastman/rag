---
paths: "docker/**/*.*, docker-compose*.yml, **/monitoring/**"
---

# Docker & Infrastructure

## Services (docker-compose.dev.yml)

### Default services (no profile — always started with `docker-core-up`)

| Container | Port | Purpose |
|-----------|------|---------|
| dev-postgres | 5432 | PostgreSQL 17 + pgvector (pgvector/pgvector:pg17) |
| dev-redis | 6379 | App cache (redis:8.6.0, volatile-lfu, 512MB) |
| dev-qdrant | 6333, 6334 | Vector DB (qdrant:v1.17.0, gRPC on 6334) |
| dev-bge-m3 | 8000 | BGE-M3 dense+sparse+ColBERT (4GB) |
| dev-user-base | 8003 | USER2-base Russian embeddings (2GB) |
| dev-docling | 5001 | Document parsing PDF/DOCX/CSV (4GB) |

### Profile-gated services

| Profile | Containers | Key Ports |
|---------|-----------|-----------|
| `bot` | dev-litellm, dev-bot | 4000 |
| `ml` | dev-clickhouse, dev-minio, dev-redis-langfuse, dev-langfuse-worker, dev-langfuse, dev-mlflow | 8123, 9090, 6380, 3001, 5000 |
| `obs` | dev-loki, dev-promtail, dev-alertmanager | 3100, 9093 |
| `ingest` | dev-ingestion | — |
| `voice` | dev-rag-api, dev-livekit, dev-livekit-sip, dev-voice-agent | 8080, 7880, 5060 |
| `security` | dev-llm-guard | 8100 |
| `full` | all of the above | — |

## Makefile Commands

```bash
COMPOSE_CMD = docker compose --compatibility -f docker-compose.dev.yml
```

| Command | Profile | Services started |
|---------|---------|-----------------|
| `make docker-up` / `make docker-core-up` | *(none)* | 6 core services |
| `make docker-bot-up` | bot | + litellm, bot (8 total) |
| `make docker-obs-up` | obs | + loki, promtail, alertmanager (9 total) |
| `make docker-ml-up` | ml | + langfuse stack + mlflow (12 total) |
| `make docker-ingest-up` | ingest | + ingestion (7 total) |
| `make docker-voice-up` | voice | + rag-api, livekit, sip, voice-agent (10 total) |
| `make docker-full-up` | full | all 23 services |
| `make docker-down` | full | stop all |
| `make docker-ps` | full | show status |

**Combining profiles manually:**
```bash
docker compose -f docker-compose.dev.yml --profile bot --profile obs up -d
COMPOSE_PROFILES=bot,obs docker compose -f docker-compose.dev.yml up -d
```

**Voice preflight:** `make docker-voice-up` checks for `docker/livekit/livekit.yaml` before starting.

## VPS Stack (docker-compose.vps.yml)

**VPS:** `admin@95.111.252.29:1654` | Alias: `ssh vps` | Path: `/opt/rag-fresh`

```bash
# Start all VPS services
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml up -d"

# With ingestion pipeline
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d"
```

| Service | Memory | Notes |
|---------|--------|-------|
| vps-postgres | 512MB | pgvector |
| vps-redis | 300MB | volatile-lfu, 256MB maxmemory |
| vps-qdrant | 1GB | |
| vps-docling | 2GB | |
| vps-bge-m3 | 4GB | Dense + ColBERT rerank |
| vps-user-base | 2GB | Semantic cache embeddings |
| vps-litellm | 512MB | |
| vps-bot | 512MB | **RERANK_PROVIDER=none** (ColBERT too slow on CPU) |
| vps-ingestion | 512MB | profile: ingest only |
| vps-clickhouse | 1.5GB | Langfuse analytics |
| vps-minio | 256MB | S3 storage (Langfuse events/media) |
| vps-redis-langfuse | 128MB | Langfuse queues |
| vps-langfuse-worker | 512MB | Langfuse background processing |
| vps-langfuse | 512MB | Langfuse UI + API (port 3001) |

**Collection:** `gdrive_documents_bge` (1024-dim BGE-M3 dense + BGE-M3 sparse, field "bm42")

### Hot Reload (no rebuild)

Volume mounts allow code updates without image rebuild:
```bash
rsync -avz src/ vps:/opt/rag-fresh/src/
ssh vps "docker restart vps-bot"   # ~5 seconds
```

Force-recreate after compose changes:
```bash
ssh vps "cd /opt/rag-fresh && docker compose -f docker-compose.vps.yml up -d --force-recreate ingestion"
```

### VPS Quick Commands

```bash
ssh vps "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vps"
ssh vps "docker logs vps-bot --tail 50"
ssh vps "docker stats --no-stream | grep vps"
ssh vps "docker system df && df -h /"
# Cleanup (careful — never prune volumes):
ssh vps "docker builder prune -f && docker image prune -f"
```

### VPS Troubleshooting

| Issue | Fix |
|-------|-----|
| Volume mounts stale | `--force-recreate` once |
| `No space left on device` | `docker builder prune -a -f` |
| Image too large (28GB+) | Use `COPY --chown` not `RUN chown -R` (avoid layer copy) |
| Container unhealthy | `docker logs vps-{service} --tail 50` |
| Code not updated | `docker inspect vps-ingestion --format '{{json .Mounts}}'` |

**Heavy VPS commands** (build, etc.) → use tmux window. See `CLAUDE.local.md`.

## LLM Gateway (LiteLLM)

```
Bot → LiteLLM Proxy (:4000) → Cerebras/Groq → Langfuse OTEL tracing
```

**Config:** `docker/litellm/config.yaml`

| Model Alias | Provider / Model | Notes |
|-------------|-----------------|-------|
| `gpt-4o-mini` | Cerebras `gpt-oss-120b` | Primary (reasoning model, 3000 tok/s) |
| `gpt-oss-120b` | Cerebras `gpt-oss-120b` | Standalone alias for benchmarking |
| `gpt-4o-mini-cerebras-glm` | Cerebras `zai-glm-4.7` | Legacy fallback |
| `gpt-4o-mini-fallback` | Groq `llama-3.1-70b-versatile` | Groq fallback |
| `gpt-4o-mini-openai` | OpenAI `gpt-4o-mini` | OpenAI fallback |
| `whisper` | OpenAI `whisper-1` | STT (audio_transcription mode) |

Note: `gpt-oss-120b` uses `merge_reasoning_content_in_choices: true` (reasoning model delta fix).

## Building Custom Images

```bash
# Build all custom services (docker compose)
docker compose -f docker-compose.dev.yml build

# Build a single service
docker compose -f docker-compose.dev.yml build bot

# Transfer image to VPS k3s
make k3s-push-bot   # docker save rag/bot:latest | ssh vps k3s ctr import
```

| Service | Dockerfile |
|---------|-----------|
| bot | `telegram_bot/Dockerfile` |
| bge-m3 | `services/bge-m3-api/Dockerfile` |
| user-base | `services/user-base/Dockerfile` |
| docling | `services/docling/Dockerfile` |
| ingestion | `Dockerfile.ingestion` |
| llm-guard | `services/llm-guard-api/Dockerfile` |
| rag-api | `src/api/Dockerfile` |
| voice-agent | `src/voice/Dockerfile` |

**Docker pattern (all custom services):**
```dockerfile
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
RUN uv sync --frozen --no-dev --no-install-project  # deps layer
COPY . .
RUN uv sync --frozen --no-dev                        # code layer
FROM python:3.12-slim-bookworm AS runtime
COPY --from=builder /app/.venv /app/.venv
```

## Monitoring & Alerting

```bash
make monitoring-up          # Start Loki, Promtail, Alertmanager
make monitoring-down        # Stop
make monitoring-status      # Check health
make monitoring-test-alert  # Send test alert to Telegram
make monitoring-logs        # View logs
```

| Container | Port | Purpose |
|-----------|------|---------|
| dev-loki | 3100 | Log aggregation |
| dev-promtail | — | Docker log collection |
| dev-alertmanager | 9093 | Alert routing to Telegram |

**Config files:** `docker/monitoring/loki.yaml`, `promtail.yaml`, `alertmanager.yaml`, `rules/`
**Env vars:** `TELEGRAM_ALERTING_BOT_TOKEN`, `TELEGRAM_ALERTING_CHAT_ID`
**Loki rules mount:** `./docker/monitoring/rules:/etc/loki/rules/fake:ro` (tenant=`fake`)
**Docs:** `docs/ALERTING.md`

## Security & Environment

**Security defaults** (applied to custom services via `x-security-defaults`):
- `no-new-privileges: true`, `cap_drop: ALL`, `read_only: true`, `tmpfs: /tmp`

**Log rotation:** 50m/5 for bot, litellm, langfuse; 10m/3 for others.

**Required env vars by profile:**

| Profile | Required |
|---------|----------|
| core | none (dev defaults OK) |
| bot | `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY` + 1 LLM provider key |
| ml | `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` |

**Verify config:**
```bash
docker compose --compatibility -f docker-compose.dev.yml config --quiet
docker inspect dev-bge-m3 --format '{{.HostConfig.Memory}}'  # != 0
TELEGRAM_BOT_TOKEN= make docker-bot-up  # Must fail with "is required"
```

**Image drift check:**
```bash
make verify-compose-images   # Check running containers match pinned digests
```

## PostgreSQL Schema (Init Scripts)

`docker/postgres/init/` scripts run on first container start:

| Script | Purpose |
|--------|---------|
| `00-init-databases.sql` | Creates databases: langfuse, mlflow, litellm, realestate |
| `02-cocoindex.sql` | CocoIndex internal tables |
| `03-unified-ingestion-alter.sql` | Ingestion state extensions |
| `04-voice-schema.sql` | Call transcripts |
| `05-realestate-schema.sql` | Apartments, projects, price history |
| `06-lead-scoring-sync.sql` | lead_scores, lead_score_sync_audit |
| `07-nurturing-funnel-analytics.sql` | nurturing_jobs, funnel_metrics_daily, scheduler_leases |
| `08-user-favorites.sql` | User favorite listings |
