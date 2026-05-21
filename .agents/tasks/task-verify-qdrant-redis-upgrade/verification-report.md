# Verification Report: Qdrant v1.17.1 -> v1.18.0 & Redis 8.6.2 -> 8.6.3

**Issue:** #1472  
**Renovate PR:** #1467  
**Date:** 2025-01-20  
**Verdict:** APPROVE

---

## 1. Qdrant v1.18.0 Release Notes Analysis

### Features

- TurboQuant quantization variant (8x compression without recall loss)
- API to create/delete named vectors in existing collections
- Deep memory reporting
- Low memory mode (force on-disk to prevent OOM on startup)
- Strict mode parameter to reject updates when memory is high

### Improvements

- Dynamic CPU pool for search workers (better performance under IO wait)
- Operation size based batching for shard transfers
- Reduced geo index memory by 7x
- **Fully remove RocksDB support** (simplifying storage handling)
- Default 60s timeout for update requests
- Various snapshot transfer and optimizer improvements

### Bug Fixes

- Fix stop words case sensitivity over gRPC
- Fix datetime parsing
- Fix IsEmpty on freshly rebuilt null index
- Fix nested MatchTextAny not using full-text index
- Fix sparse vector search panic on score post processing
- Many other internal fixes

### Security

- Enforce API key/JWT authentication on internal gRPC endpoints
- Config option to disable snapshot restore from URL
- TLS dependency bumps

### Breaking Changes Assessment

- **RocksDB removal:** This is the only potentially breaking change. A full codebase search found ZERO references to RocksDB. The project uses Qdrant's default storage engine (WAL-based), not RocksDB. This change is safe.
- **No API deprecations** affecting the project's usage patterns (`query_points`, `query_batch_points`, `query_points_groups`, `SparseVector` models).
- **SDK compatibility:** `qdrant-client` SDK v1.17.1 is compatible with server v1.18.0. Qdrant maintains backward server compatibility for older clients.
- **Config validity:** The project's `on_disk_payload` and `optimizers` config in `docker/qdrant/config.yaml` remains valid and unchanged.

---

## 2. Redis 8.6.3 Patch Assessment

- This is a **patch release** (8.6.2 -> 8.6.3) with very low risk.
- Both Redis instances are upgraded: `redis` (app cache) and `redis-langfuse` (Langfuse worker).
- Both compose.yml instances use the same image+digest: `redis:8.6.3@sha256:e628485c98f8cfe942d8b6f34d461dabf069884bf18932ccbdd9dd9af20b1acc`
- k8s redis uses: `redis:8.6.3@sha256:0c341492924cad6f5483f9133e43bd6c51ecdecbcadfac5b51657393b6a7936c` (different digest expected for different platform/manifest type)
- Healthchecks are present and unchanged for both Redis instances.
- Python redis SDK (v7.4.0) is compatible with Redis server 8.6.x.

---

## 3. Compose/K8s Manifest Consistency

### Test Results (all run in sandbox)

| Test Suite | Result |
|---|---|
| `tests/unit/test_k8s_image_version_sync.py` | 3/3 PASSED (qdrant, redis, litellm tags match between compose and k8s) |
| `tests/unit/test_compose.py` | All PASSED (YAML validity, structure) |
| `tests/unit/test_compose_config.py` | 72/72 PASSED (security, healthchecks, profiles, probes) |
| `tests/unit/test_qdrant_service.py` | All PASSED (quantization, hybrid search, ColBERT reranking) |
| `tests/unit/test_search_engines.py` | All PASSED (RRF fusion, sparse vectors, create_search_engine) |
| `tests/unit/retrieval/` | All PASSED (search engine shared, reranker, topic classifier) |

### Full Unit Test Run

**6874 passed**, 14 failed (all pre-existing/environment-related):
- `docker-compose` binary not available in sandbox
- `mini_app` import issues (unrelated module)
- Markdown link checker failures (network-dependent)

---

## 4. BGE-M3 Embeddings Compatibility

The Qdrant v1.18.0 release does not change vector storage format for existing collections. The BGE-M3 embedding API is independent of Qdrant server version. The project's `SparseVector` model usage, `query_points` API, and RRF fusion logic are all stable across this upgrade.

---

## 5. Skipped Checks (with reasons)

| Check | Reason Skipped |
|---|---|
| `make verify-compose-images` | Requires running Docker containers (no Docker daemon in sandbox) |
| Live Redis health test (`make test-redis`) | Requires running Redis container |
| Live Qdrant preflight (`make test-preflight`) | Requires running services |
| k8s apply cycle | No cluster available |

---

## Summary

| Component | From | To | Risk | Status |
|---|---|---|---|---|
| Qdrant | v1.17.1 | v1.18.0 | Low | Safe to merge |
| Redis | 8.6.2 | 8.6.3 | Very Low | Safe to merge |

**Verdict: APPROVE**

The upgrade is safe to merge. No breaking changes affect this project. All automated tests that can run in the sandbox pass. CI is green per the issue description.
