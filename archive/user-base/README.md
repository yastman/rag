# USER2-base Russian Dense Embedding Service

Standalone FastAPI service for generating dense vectors using `deepvk/USER2-base` for Russian-language semantic matching.

## Purpose

Provides high-quality Russian dense embeddings (768-dim) for retrieval and semantic search paths that need native-language coverage beyond BGE-M3.

## Entrypoint

- **Application**: [`main.py`](main.py)
- **Dockerfile**: [`Dockerfile`](Dockerfile)

## Docker

- **Service name**: `user-base`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../../DOCKER.md`](../../DOCKER.md) for contract details)
- **Local port**: `8003` (host) mapped from container port `8000`
- **Health**: `GET http://localhost:8003/health`

## Quick Start

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d user-base
curl -fsS http://localhost:8003/health
```

## Optional ONNX Backend

Set `EMBEDDING_BACKEND=onnx` for ~1.5–3× CPU inference speedup (requires `onnxruntime` + `optimum`).

## Tests & Checks

```bash
# Unit tests
uv run pytest tests/unit/test_userbase_endpoints.py -v

# Dockerfile validation
uv run pytest tests/unit/test_userbase_dockerfile_permissions.py tests/unit/test_dockerfile_python_abi.py -v -k user-base

# Smoke (requires running service)
uv run pytest tests/smoke/test_zoo_smoke.py -v -k user_base
```

## Owner Boundaries

- Model load, warmup, and dense embedding inference
- Optional ONNX backend switching
- Healthcheck endpoint

Do not change the internal port (`8000`) or healthcheck path without updating `compose.yml` and downstream vectorizer clients.
