# Local Service Containers

This directory contains standalone service containers that support the RAG runtime.
They are referenced from the main [`compose.yml`](../compose.yml) and started as part of the Docker Compose stack.

> For Compose operations, profiles, and env requirements, see [`../DOCKER.md`](../DOCKER.md).

## Services

| Service | Purpose | Entrypoint | Docker service | Profile | Local URL |
|---|---|---|---|---|---|
| `bge-m3-api/` | Multi-vector embeddings (dense, sparse, ColBERT) | [`app.py`](bge-m3-api/app.py) | `bge-m3` | — (default) | http://localhost:8000 |

> **Docling** runs in-process via the native Python SDK (`src/ingestion/`). There is no
> HTTP sidecar for document parsing. The `services/docling/` directory is archived
> reference material from the pre-migration HTTP approach and is no longer part of the
> active stack.

## Quick Validation

Build and health-check a single service:

```bash
# bge-m3
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose build bge-m3
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d bge-m3
curl -fsS http://localhost:8000/health
```

## Tests & Checks

| Service | Unit tests | Dockerfile checks | Smoke tests |
|---|---|---|---|
| `bge-m3` | `tests/unit/test_bge_m3_endpoints.py`, `tests/unit/test_bge_m3_rerank.py` | `tests/unit/test_docker_static_validation.py` | `tests/smoke/test_zoo_smoke.py` |

Run all relevant unit tests:

```bash
make test-unit
```

## Owner Boundaries

- **bge-m3-api**: embedding model serving, metrics export, healthchecks

Do not modify the application code in these directories without also verifying the corresponding Compose health checks and `make verify-compose-images` after image pin updates.

## See Also

- [`../DOCKER.md`](../DOCKER.md) — Compose profiles, env requirements, and service map
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation flow
- [`../docs/runbooks/README.md`](../docs/runbooks/README.md) — Operational troubleshooting
