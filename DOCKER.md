***REMOVED*** Docker Services

Overview of Docker containers for RAG pipeline development and production.

***REMOVED******REMOVED*** Quick Start

```bash
***REMOVED*** Development stack (all services)
docker compose -f docker-compose.dev.yml up -d

***REMOVED*** Minimal local stack (Qdrant, Redis, BGE-M3, Docling)
docker compose -f docker-compose.local.yml up -d

***REMOVED*** Stop services
docker compose -f docker-compose.dev.yml down

***REMOVED*** Reset (remove volumes)
docker compose -f docker-compose.dev.yml down -v
```

***REMOVED******REMOVED*** Compose Files

| File | Purpose |
|------|---------|
| [docker-compose.dev.yml](./docker-compose.dev.yml) | Full dev stack with bot, ML platform, all AI services |
| [docker-compose.local.yml](./docker-compose.local.yml) | Minimal stack for local development |

***REMOVED******REMOVED*** Services (docker-compose.dev.yml)

***REMOVED******REMOVED******REMOVED*** Databases

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **postgres** | dev-postgres | 5432 | PostgreSQL + pgvector for Langfuse/MLflow |
| **redis** | dev-redis | 6379 | Redis 8.4 (cache, Query Engine) |
| **qdrant** | dev-qdrant | 6333, 6334 | Vector database. UI: http://localhost:6333/dashboard |

***REMOVED******REMOVED******REMOVED*** AI Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **bge-m3** | dev-bge-m3 | 8000 | BGE-M3 embeddings (dense + sparse + ColBERT) |
| **bm42** | dev-bm42 | 8002 | BM42 sparse embeddings (FastEmbed) |
| **user-base** | dev-user-base | 8003 | User embeddings service |
| **docling** | dev-docling | 5001 | Document parsing (PDF, DOCX, images) |
| **lightrag** | dev-lightrag | 9621 | LightRAG graph-based retrieval |

***REMOVED******REMOVED******REMOVED*** ML Platform

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **langfuse** | dev-langfuse | 3001 | LLM tracing. UI: http://localhost:3001 |
| **mlflow** | dev-mlflow | 5000 | Experiment tracking. UI: http://localhost:5000 |

***REMOVED******REMOVED******REMOVED*** Application

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **bot** | dev-bot | — | Telegram bot (Voyage AI powered) |

***REMOVED******REMOVED*** Memory Requirements

| Service | Memory Limit | Notes |
|---------|--------------|-------|
| bge-m3 | 4GB | Heavy model, needs warm-up |
| docling | 4GB | Document parsing with OCR |
| user-base | 2GB | User embeddings |
| bm42 | 1GB | Lightweight sparse encoder |
| bot | 512MB | Telegram bot |

**Total recommended:** 16GB+ RAM for full dev stack.

***REMOVED******REMOVED*** Health Checks

```bash
***REMOVED*** Check all services
docker compose -f docker-compose.dev.yml ps

***REMOVED*** Check specific service logs
docker logs dev-bot -f
docker logs dev-qdrant -f

***REMOVED*** Test endpoints
curl http://localhost:6333/healthz       ***REMOVED*** Qdrant
curl http://localhost:8000/health        ***REMOVED*** BGE-M3
curl http://localhost:5001/health        ***REMOVED*** Docling
curl http://localhost:3001/api/public/health  ***REMOVED*** Langfuse
```

***REMOVED******REMOVED*** Environment Variables

Required in `.env`:

```bash
***REMOVED*** Telegram
TELEGRAM_BOT_TOKEN=[REDACTED-TELEGRAM-TOKEN]

***REMOVED*** Voyage AI
VOYAGE_API_KEY=your_voyage_key

***REMOVED*** LLM (Cerebras default)
LLM_API_KEY=your_llm_key
LLM_BASE_URL=https://api.cerebras.ai/v1
LLM_MODEL=qwen-3-32b

***REMOVED*** Optional
OPENAI_API_KEY=[REDACTED-OPENAI-KEY]  ***REMOVED*** For LightRAG
```

***REMOVED******REMOVED*** Volumes

| Volume | Service | Data |
|--------|---------|------|
| postgres_data | postgres | Langfuse/MLflow databases |
| redis_data | redis | Cache, RediSearch indexes |
| qdrant_data | qdrant | Vector collections |
| bge_models | bge-m3 | Downloaded model weights |
| lightrag_data | lightrag | Graph storage |
| mlflow_artifacts | mlflow | Experiment artifacts |

***REMOVED******REMOVED*** Service URLs (Internal Network)

When services communicate inside Docker:

```python
REDIS_URL = "redis://redis:6379"
QDRANT_URL = "http://qdrant:6333"
BM42_URL = "http://bm42:8000"
BGE_M3_URL = "http://bge-m3:8000"
DOCLING_URL = "http://docling:5001"
```

***REMOVED******REMOVED*** Common Commands

```bash
***REMOVED*** Rebuild specific service
docker compose -f docker-compose.dev.yml build bot
docker compose -f docker-compose.dev.yml up -d bot

***REMOVED*** View real-time logs
docker compose -f docker-compose.dev.yml logs -f bot redis qdrant

***REMOVED*** Enter container shell
docker exec -it dev-bot bash
docker exec -it dev-redis redis-cli

***REMOVED*** Check resource usage
docker stats
```

***REMOVED******REMOVED*** Image Versioning Policy

| Type | Strategy | Example |
|------|----------|---------|
| Stable 3rd-party | Versioned tag | `redis:8.4.0`, `qdrant/qdrant:v1.16`, `clickhouse:24.8` |
| Floating tag only | Digest pin | `docling-serve-cpu@sha256:4e93e8e...` |
| Self-built | Local build | `services/bm42/Dockerfile` |

**Rules:**
- Never use `latest` or `main` tags in compose files
- Versioned tags (semver, release tags, version numbers) are sufficient for reproducibility
- Digest pinning required only when no stable tag exists (e.g., Docling)
- Update tags explicitly via Renovate PR or manual bump

**Current pinned digests:**
- `ghcr.io/docling-project/docling-serve-cpu@sha256:4e93e8ec95accd74474a60d0cbbd1292b333bba2c53bb43074ae966d3f1becc8`
- `quay.io/docling-project/docling-serve@sha256:0acc75bd86219a8c8cdf38970cb651b0567844d6c97ec9d9023624c8209c6efc`

***REMOVED******REMOVED*** Required Environment Variables

| Profile | Required Variables | Notes |
|---------|-------------------|-------|
| core | None | Dev defaults for postgres/redis/qdrant |
| bot | TELEGRAM_BOT_TOKEN, VOYAGE_API_KEY, LITELLM_MASTER_KEY | + at least one LLM provider |
| ml | NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY | Crypto keys for Langfuse |
| full | All of the above | |

**LLM Providers:** At least one of CEREBRAS_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY must be set for the bot profile. LiteLLM uses fallback chain: Cerebras → Groq → OpenAI.

**Behavior:** Missing required variables cause compose to abort immediately with a clear error message (e.g., "TELEGRAM_BOT_TOKEN is required").

***REMOVED******REMOVED*** Related

- [CLAUDE.md](./CLAUDE.md) — Full architecture documentation
- [telegram_bot/Dockerfile](./telegram_bot/Dockerfile) — Bot container
- [services/](./services/) — Custom service Dockerfiles
