# BGE-M3 sidecar

Applies to services/bge-m3-api/**. Extends [service rules](../AGENTS.override.md)
and [root AGENTS](../../AGENTS.md).

- Preserve /health, /encode, /rerank and Prometheus metric contracts.
- app.py owns model lifecycle/inference; config.py owns settings.
- pyproject.toml and uv.lock own this image's dependencies; there is no requirements.txt.
- artifact_manifest.json, fetch_artifact.py, and verify_artifact.py own artifact provenance.
  Do not substitute a test fixture for a real model or claim unit tests prove an image builds.
- Keep port 8000, health path, and downstream request/response expectations aligned with
  Compose and the actual src/runtime and src/services consumers.
- Never assume a single host's artifact path or embed credentials.

## Checks

For service-local dependency work, sync in this directory with `uv sync --frozen`.
For mocked endpoint tests, run from the repository root:

```bash
uv sync --frozen --extra bge-extras
uv run --no-sync pytest tests/unit/test_bge_m3_endpoints.py tests/unit/test_bge_m3_rerank.py -q
uv run --no-sync pytest tests/unit/test_bge_m3_artifact.py -q
uv run --no-sync pytest tests/unit/test_docker_static_validation.py -q -k "bge_m3 or bge-m3"
```

Artifact/image changes also require the real build and offline smoke in [README](README.md).
[DOCKER.md](../../DOCKER.md) and [Tests](../../tests/README.md) own deployment and lane setup.
