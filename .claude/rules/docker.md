---
paths: "docker/**/*.*, docker-compose*.yml"
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
