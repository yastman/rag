# Docker Services

Overview of Docker containers for RAG pipeline development and production.

## Quick Start

```bash
# Development stack (all services)
docker compose -f docker-compose.dev.yml up -d

# Minimal local stack (Qdrant, Redis, BGE-M3, Docling)
docker compose -f docker-compose.local.yml up -d

# Stop services
docker compose -f docker-compose.dev.yml down

# Reset (remove volumes)
docker compose -f docker-compose.dev.yml down -v
```

## Compose Files

| File | Purpose |
|------|---------|
| [docker-compose.dev.yml](./docker-compose.dev.yml) | Full dev stack with bot, ML platform, all AI services |
| [docker-compose.local.yml](./docker-compose.local.yml) | Minimal stack for local development |

## Services (docker-compose.dev.yml)

### Databases

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **postgres** | dev-postgres | 5432 | PostgreSQL + pgvector for Langfuse/MLflow |
| **redis** | dev-redis | 6379, 8001 | Redis Stack (cache, RediSearch). UI: http://localhost:8001 |
| **qdrant** | dev-qdrant | 6333, 6334 | Vector database. UI: http://localhost:6333/dashboard |

### AI Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **bge-m3** | dev-bge-m3 | 8000 | BGE-M3 embeddings (dense + sparse + ColBERT) |
| **bm42** | dev-bm42 | 8002 | BM42 sparse embeddings (FastEmbed) |
| **user-base** | dev-user-base | 8003 | User embeddings service |
| **docling** | dev-docling | 5001 | Document parsing (PDF, DOCX, images) |
| **lightrag** | dev-lightrag | 9621 | LightRAG graph-based retrieval |

### ML Platform

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **langfuse** | dev-langfuse | 3001 | LLM tracing. UI: http://localhost:3001 |
| **mlflow** | dev-mlflow | 5000 | Experiment tracking. UI: http://localhost:5000 |

### Application

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **bot** | dev-bot | — | Telegram bot (Voyage AI powered) |

## Memory Requirements

| Service | Memory Limit | Notes |
|---------|--------------|-------|
| bge-m3 | 4GB | Heavy model, needs warm-up |
| docling | 4GB | Document parsing with OCR |
| user-base | 2GB | User embeddings |
| bm42 | 1GB | Lightweight sparse encoder |
| bot | 512MB | Telegram bot |

**Total recommended:** 16GB+ RAM for full dev stack.

## Health Checks

```bash
# Check all services
docker compose -f docker-compose.dev.yml ps

# Check specific service logs
docker logs dev-bot -f
docker logs dev-qdrant -f

# Test endpoints
curl http://localhost:6333/healthz       # Qdrant
curl http://localhost:8000/health        # BGE-M3
curl http://localhost:5001/health        # Docling
curl http://localhost:3001/api/public/health  # Langfuse
```

## Environment Variables

Required in `.env`:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# Voyage AI
VOYAGE_API_KEY=your_voyage_key

# LLM (Cerebras default)
LLM_API_KEY=your_llm_key
LLM_BASE_URL=https://api.cerebras.ai/v1
LLM_MODEL=qwen-3-32b

# Optional
OPENAI_API_KEY=sk-...  # For LightRAG
```

## Volumes

| Volume | Service | Data |
|--------|---------|------|
| postgres_data | postgres | Langfuse/MLflow databases |
| redis_data | redis | Cache, RediSearch indexes |
| qdrant_data | qdrant | Vector collections |
| bge_models | bge-m3 | Downloaded model weights |
| lightrag_data | lightrag | Graph storage |
| mlflow_artifacts | mlflow | Experiment artifacts |

## Service URLs (Internal Network)

When services communicate inside Docker:

```python
REDIS_URL = "redis://redis:6379"
QDRANT_URL = "http://qdrant:6333"
BM42_URL = "http://bm42:8000"
BGE_M3_URL = "http://bge-m3:8000"
DOCLING_URL = "http://docling:5001"
```

## Common Commands

```bash
# Rebuild specific service
docker compose -f docker-compose.dev.yml build bot
docker compose -f docker-compose.dev.yml up -d bot

# View real-time logs
docker compose -f docker-compose.dev.yml logs -f bot redis qdrant

# Enter container shell
docker exec -it dev-bot bash
docker exec -it dev-redis redis-cli

# Check resource usage
docker stats
```

## Related

- [CLAUDE.md](./CLAUDE.md) — Full architecture documentation
- [telegram_bot/Dockerfile](./telegram_bot/Dockerfile) — Bot container
- [services/](./services/) — Custom service Dockerfiles
