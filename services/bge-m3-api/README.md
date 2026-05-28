# BGE-M3 Multi-Vector Embedding Service

Standalone FastAPI service that generates dense, sparse, and ColBERT embeddings via BGE-M3 ONNX INT8 runtime.

## Purpose

Used by the ingestion pipeline and query contextualization to produce multi-vector representations for RAG retrieval. Uses `philipchung/bge-m3-onnx` INT8-quantised model via `onnxruntime.InferenceSession`.

## Entrypoint

- **Application**: [`app.py`](app.py)
- **Dockerfile**: [`Dockerfile`](Dockerfile)

## Model Deployment

The ONNX INT8 model (`model.int8.onnx` + `model.int8.onnx.data`) is baked into the Docker image at build time via a BuildKit named context. The container does not require a runtime bind mount.

- **Build-time baking (default)**: The Dockerfile uses `RUN --mount=type=bind,from=bge_m3_onnx_model,...` to copy the artifacts into `/models/onnx` inside the image. `BGE_M3_ONNX_MODEL_HOST_DIR` points Docker BuildKit to the host directory containing the ONNX artifacts and is consumed during `docker compose build`, NOT at `docker compose up`.
- **Config-driven**: The default `ONNX_MODEL_DIR` is `/models/onnx` (set in the Dockerfile and `config.py`). Override via the `ONNX_MODEL_DIR` env var if using a non-standard path.

For local development with Docker, set `BGE_M3_ONNX_MODEL_HOST_DIR` in `.env` to the absolute host path containing `model.int8.onnx` and `model.int8.onnx.data`.

## Docker

- **Service name**: `bge-m3`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../../DOCKER.md`](../../DOCKER.md) for contract details)
- **Local port**: `8000` (mapped in `compose.dev.yml`)
- **Health**: `GET http://localhost:8000/health`
- **Metrics**: Prometheus metrics exposed internally (ASGI app mounted at `/metrics`)

## Quick Start

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d bge-m3
curl -fsS http://localhost:8000/health
```

## Tests & Checks

```bash
# Unit tests
uv run pytest tests/unit/test_bge_m3_endpoints.py tests/unit/test_bge_m3_rerank.py -v

# Dockerfile validation
uv run pytest tests/unit/test_docker_static_validation.py -v -k bge-m3

# Smoke (requires running service)
uv run pytest tests/smoke/test_zoo_smoke.py -v -k bge_m3
```

## Owner Boundaries

- ONNX session loading, warmup, and inference lifecycle
- Prometheus metrics (`bge_encode_requests_total`, `bge_encode_seconds`, etc.)
- Healthcheck endpoint

Do not change the port, healthcheck path, or metrics shape without updating `compose.yml` and downstream consumers in `src/retrieval/`.
