# DOCKER.md — Compose Runtime Reference

Docker Compose is the primary runtime for all sidecar services. The Python
application runs as a native process (or as the `bot` Compose service for
production-like deploys).

## Compose Files

| File | Purpose |
|---|---|
| `compose.yml` | Base configuration — all services, no ports exposed |
| `compose.dev.yml` | Dev overrides — ports, relaxed caps, dev tuning |
| `compose.core.yml` | Minimal core (Qdrant + Redis only, no auth) |

Local dev uses both base and override:

```
COMPOSE_FILE=compose.yml:compose.dev.yml
```

This is the default in `.env.example` and used by all `make` targets.

## Profiles

Services are gated by profiles. Run only what you need.

| Profile | Services included |
|---|---|
| *(no profile)* | `postgres`, `redis`, `qdrant`, `bge-m3` |
| `bot` | above + `bot` |
| `ingest` | above + `docling`, `ingestion` |
| `full` | all services |

## Services

| Service | Image | Profile | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | default | Conversation history, ingestion tracking |
| `redis` | `redis:8.6.3` | default | Five caches: semantic answer, embedding, search, rerank, extraction |
| `qdrant` | `qdrant/qdrant:v1.18.1` | default | Vector store — dense, sparse, ColBERT retrieval |
| `bge-m3` | built locally | default | Self-hosted BGE-M3 ONNX embedding API |
| `bot` | built locally | `bot` | Telegram bot process |
| `docling` | built locally | `ingest` | Document parsing (PDF, etc.) |
| `ingestion` | built locally | `ingest` | Unified ingestion pipeline |

## Ports (dev only — `compose.dev.yml`)

Base `compose.yml` exposes **no ports**. All ports are loopback-bound in dev.

| Service | Port | Protocol |
|---|---|---|
| `qdrant` | `127.0.0.1:6333` | HTTP REST |
| `qdrant` | `127.0.0.1:6334` | gRPC |
| `redis` | `127.0.0.1:6379` | Redis |
| `postgres` | `127.0.0.1:5432` | PostgreSQL |
| `bge-m3` | `127.0.0.1:8000` | HTTP |
| `docling` | `127.0.0.1:5001` | HTTP |

## Common Commands

```bash
# Minimal core (Qdrant + Redis, no auth — fastest start for native dev)
make core-min-up

# Full default core (postgres, redis, qdrant, bge-m3)
make core-up

# Core + bot (Compose-managed bot)
make docker-bot-up

# Core + ingestion (docling + ingestion pipeline)
make docker-ingest-up

# Full stack (all profiles)
make docker-full-up

# Status
make docker-ps

# Stop everything
make docker-down

# Prune build cache and stopped containers (safe)
make docker-clean
```

Native bot run (bot as host process, sidecars in Compose):

```bash
make core-up      # start sidecars
make run-bot      # run bot natively
```

## Required Environment Variables

Copy `.env.example` to `.env` and fill in at minimum:

| Variable | Required for | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | all profiles | Any non-empty string for local dev |
| `REDIS_PASSWORD` | all profiles | Any non-empty string for local dev |
| `TELEGRAM_BOT_TOKEN` | `bot` profile | From @BotFather |
| `BGE_M3_ONNX_MODEL_HOST_DIR` | `bge-m3` build | Path to ONNX INT8 model dir; baked into image at build time |
| `CEREBRAS_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | LLM calls | At least one required |

## BGE-M3 Build Requirement

`bge-m3` is a locally-built image. The ONNX model directory is baked into the
image at build time via a BuildKit named context — it is **not** bind-mounted
at runtime.

```bash
BGE_M3_ONNX_MODEL_HOST_DIR=./path/to/bge_m3_onnx_int8
```

The directory must contain `model.int8.onnx` (and its `.data` sidecar) before
running `docker compose build bge-m3`.

## Memory Limits

| Service | Default limit |
|---|---|
| `postgres` | 512 MB |
| `redis` | 300 MB (256 MB on VPS) |
| `qdrant` | 1 GB |
| `bge-m3` | 4 GB (override: `BGE_M3_MEMORY_LIMIT`) |
| `bot` | 512 MB |
| `docling` | 2 GB |
| `ingestion` | 1 GB |

## Health Checks

All services declare health checks. Dependent services use `condition:
service_healthy`. On first start, `bge-m3` has a 420 s start period (cold
model load).

## Volumes

| Volume | Service |
|---|---|
| `postgres_data` | `postgres` |
| `redis_data` | `redis` |
| `qdrant_data` | `qdrant` |
| `hf_cache` | `bge-m3` |
| `docling_cache` | `docling` |
| `ingestion-manifest` | `ingestion` |

## Security Defaults

`compose.yml` applies hardened defaults to all services:
`no-new-privileges`, `cap_drop: ALL`, `read_only: true`. The dev override
(`compose.dev.yml`) relaxes caps on `postgres` as needed for local startup.

## Related Docs

| Document | Use it for |
|---|---|
| [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) | Full local setup and validation ladder |
| [`docs/INGESTION.md`](docs/INGESTION.md) | Ingestion operations |
| [`docs/QDRANT_STACK.md`](docs/QDRANT_STACK.md) | Vector schema and Qdrant operations |
