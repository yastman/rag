# BGE-M3 Multi-Vector Embedding Service

Standalone FastAPI service that generates dense, sparse, and ColBERT embeddings via a pinned, hash-verified BGE-M3 ONNX artifact.

## Purpose

Used by the ingestion pipeline and query contextualization to produce multi-vector representations for RAG retrieval. Runs the fp32 all-three-output ONNX export of `philipchung/bge-m3-onnx` (MIT) via `onnxruntime.InferenceSession`. The container is strictly offline: it never downloads anything at build or startup.

## Entrypoint

- **Application**: [`app.py`](app.py)
- **Dockerfile**: [`Dockerfile`](Dockerfile)

## Pinned artifact provenance

| Field | Value |
| --- | --- |
| Source repo | `philipchung/bge-m3-onnx` (Hugging Face) |
| Immutable revision | `92465a6ca57117003d558c98578592456005d5ca` |
| License | MIT (derivative of MIT `BAAI/bge-m3` @ `5617a9f61b028005a4858fdac845db406aefb181`) |
| ONNX contract | inputs `input_ids`, `attention_mask` (int64); outputs `dense_vecs` [B,1024], `sparse_vecs` [B,L,1], `colbert_vecs` [B,L-1,1024], in this order |
| Opset | 17 (verified by direct graph inspection) |
| Tokenizer | bundled from the same revision; `tokenizer.json` sha256 `6710678b…` is byte-identical to `BAAI/bge-m3` at the pinned upstream revision |
| Files | full sizes + SHA-256 in [`artifact_manifest.json`](artifact_manifest.json) |
| Known caveat | `model.onnx_data` is 6.81 GB (~3× the fp32 backbone; historical export bloat). Loading is unaffected; shrinking it is deferred optimization |

The runtime ONNX output names/order are asserted by `ONNXEmbeddingModel.EXPECTED_OUTPUTS`, so a wrong artifact cannot silently load.

int8 is intentionally **not** selected: no int8 export exposes all three outputs with parity evidence against an approved reference. Optimization is deferred until a documented parity threshold exists.

## Artifact acquisition (one command, outside any startup path)

```bash
cd services/bge-m3-api
uv run python fetch_artifact.py --dest ../../logs/bge_m3_onnx_int8
```

This downloads every manifest-listed file from the immutable revision and verifies sizes + SHA-256 before declaring success. The default destination matches `BGE_M3_ONNX_MODEL_HOST_DIR` in `.env.example`; `logs/` is gitignored — never commit artifacts, caches, or tokenizers.

## Verification layers (all three must pass)

1. **Fetch**: `fetch_artifact.py` verifies after download.
2. **Docker build**: `Dockerfile` runs `verify_artifact.py` against the `bge_m3_onnx_model` build context before baking — the tiny dummy fixtures in `tests/fixtures/bge_m3_onnx_model/` are render-only and fail the build with an actionable error. `make docker-full-up` therefore cannot silently substitute them.
3. **Runtime startup**: `get_model()` re-verifies the baked manifest (missing files, missing shards, size/hash mismatches fail before the ONNX session exists), then loads the tokenizer from `/models/artifact/tokenizer` with `local_files_only=True` under `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`.

## Docker

- **Service name**: `bge-m3`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../../DOCKER.md`](../../DOCKER.md) for contract details)
- **Local port**: `8000` (mapped in `compose.dev.yml`)
- **Health**: `GET http://localhost:8000/health`
- **Metrics**: Prometheus metrics exposed internally (ASGI app mounted at `/metrics`)

### Build and offline smoke (exact commands)

```bash
# from the repo root, with the verified artifact dir:
BGE_M3_ONNX_MODEL_HOST_DIR=./logs/bge_m3_onnx_int8 \
  docker compose -f compose.yml -f compose.dev.yml build bge-m3

# network-disabled smoke: no ports, no volumes, fresh empty HF cache layer.
# Prints "OFFLINE SMOKE PASS" and exits 0 only when dense+sparse+ColBERT all
# pass dimension/cardinality checks on RU/BG/EN fixtures.
docker run --rm --network none --no-healthcheck --memory 6g \
  "$(docker compose -f compose.yml -f compose.dev.yml config bge-m3 | awk '/^    image:/{print $2; exit}')" \
  python /app/smoke_offline.py
```

## Image provenance and rollback

- The image bakes the manifest, so `docker run <image> cat /models/artifact/artifact_manifest.json` records the exact source revision, files, and hashes inside every image.
- Record the built image ID/digest at build time (`docker images --digests <image>`). Rollback = re-pull/re-tag the previous image digest; keep the previous artifact directory on disk. Never delete shared volumes or caches automatically.

## Quick Start

```bash
docker compose -f compose.yml -f compose.dev.yml up -d bge-m3
curl -fsS http://localhost:8000/health
```

## Tests & Checks

```bash
# Unit tests
uv run pytest tests/unit/test_bge_m3_endpoints.py tests/unit/test_bge_m3_rerank.py -v

# Artifact/offline contract
uv run pytest tests/unit/test_bge_m3_artifact.py -v

# Dockerfile validation
uv run pytest tests/unit/test_docker_static_validation.py -v -k "bge_m3 or bge-m3"

# Smoke (requires running service)
uv run pytest tests/smoke/test_zoo_smoke.py -v -k bge_m3
```

## Owner Boundaries

- ONNX session loading, warmup, and inference lifecycle
- Prometheus metrics (`bge_encode_requests_total`, `bge_encode_seconds`, etc.)
- Healthcheck endpoint

Do not change the port, healthcheck path, or metrics shape without updating `compose.yml` and downstream consumers in `src/retrieval/`.
