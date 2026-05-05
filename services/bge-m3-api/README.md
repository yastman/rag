***REMOVED*** BGE-M3 Multi-Vector Embedding Service

Standalone FastAPI service that generates dense, sparse, and ColBERT embeddings via the BGE-M3 model.

***REMOVED******REMOVED*** Purpose

Used by the ingestion pipeline and query contextualization to produce multi-vector representations for RAG retrieval.

***REMOVED******REMOVED*** Entrypoint

- **Application**: [`app.py`](app.py)
- **Dockerfile**: [`Dockerfile`](Dockerfile)

***REMOVED******REMOVED*** Docker

- **Service name**: `bge-m3`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../DOCKER.md`](../DOCKER.md) for contract details)
- **Local port**: `8000` (mapped in `compose.dev.yml`)
- **Health**: `GET http://localhost:8000/health`
- **Metrics**: Prometheus metrics exposed internally (ASGI app mounted at `/metrics`)

***REMOVED******REMOVED*** Quick Start

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d bge-m3
curl -fsS http://localhost:8000/health
```

***REMOVED******REMOVED*** Tests & Checks

```bash
***REMOVED*** Unit tests
uv run pytest tests/unit/test_bge_m3_endpoints.py tests/unit/test_bge_m3_rerank.py -v

***REMOVED*** Dockerfile validation
uv run pytest tests/unit/test_docker_static_validation.py -v -k bge-m3

***REMOVED*** Smoke (requires running service)
uv run pytest tests/smoke/test_zoo_smoke.py -v -k bge_m3
```

***REMOVED******REMOVED*** Owner Boundaries

- Model loading, warmup, and inference lifecycle
- Prometheus metrics (`bge_encode_requests_total`, `bge_encode_seconds`, etc.)
- Healthcheck endpoint

Do not change the port, healthcheck path, or metrics shape without updating `compose.yml` and downstream consumers in `src/retrieval/`.
