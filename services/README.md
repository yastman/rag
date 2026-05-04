# Local Service Containers

This directory contains standalone service containers that support the RAG runtime.
They are referenced from the main [`compose.yml`](../compose.yml) and started as part of the Docker Compose stack.

## Services

### `bge-m3-api/` — Multi-Vector Embedding Service

- **Role**: Generates dense, sparse, and ColBERT embeddings via the BGE-M3 model for document ingestion and query contextualization.
- **Entrypoint**: [`services/bge-m3-api/app.py`](bge-m3-api/app.py)
- **Dockerfile**: [`services/bge-m3-api/Dockerfile`](bge-m3-api/Dockerfile)
- **Runtime**: uv-synced multi-stage build (Python 3.14, non-root user, Prometheus metrics exposed)
- **Health**: `http://localhost:8000/health`

### `docling/` — Document Parsing Service

- **Role**: Converts PDFs and other documents into structured markdown/HTML for the unified ingestion pipeline.
- **Entrypoint**: `docling-serve` (Docling CLI serve mode, configured via environment)
- **Dockerfile**: [`services/docling/Dockerfile`](docling/Dockerfile)
- **Runtime**: CPU-only PyTorch build with uv lockfile, non-root `docling` user
- **Health**: `http://localhost:5001/health`

### `user-base/` — Russian Dense Embedding Service

- **Role**: Generates dense vectors using `deepvk/USER2-base` for Russian-language semantic matching.
- **Entrypoint**: [`services/user-base/main.py`](user-base/main.py)
- **Dockerfile**: [`services/user-base/Dockerfile`](user-base/Dockerfile)
- **Runtime**: uv-synced multi-stage build, optional ONNX backend via `EMBEDDING_BACKEND=onnx`
- **Health**: `http://localhost:8003/health` (container-internal: port `8000`)

## Validation Boundaries

These containers are safe to validate independently:

```bash
# Build and health-check a single service
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose build bge-m3
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d bge-m3
curl -fsS http://localhost:8000/health

COMPOSE_FILE=compose.yml:compose.dev.yml docker compose build docling
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d docling
curl -fsS http://localhost:5001/health

COMPOSE_FILE=compose.yml:compose.dev.yml docker compose build user-base
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d user-base
curl -fsS http://localhost:8003/health
```

Do not modify the application code in these directories without also verifying the corresponding Compose health checks and `make verify-compose-images` after image pin updates.

## See Also

- [`../DOCKER.md`](../DOCKER.md) — Compose profiles, env requirements, and service map.
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation flow.
