# Issue Draft: SDK-First Cleanup + Docker Hardening

Date: 2026-02-13
Scope: whole repository (`src/**`, `telegram_bot/**`, `services/**`, `docker-compose*.yml`, `*Dockerfile`)

## Summary
Repository still contains several custom implementations where official SDK-first paths already exist, plus a few Docker/runtime risks.

## Findings (prioritized)

### P0

1. Unit test suite is currently broken by RedisVL module mocking.
   - Evidence:
     - `tests/unit/graph/test_cache_nodes.py:14`
     - `tests/unit/graph/test_cache_nodes.py:26`
     - `tests/unit/integrations/test_cache_layers.py:18`
     - `tests/unit/integrations/test_cache_layers.py:30`
   - Problem:
     - Tests inject `sys.modules["redisvl"] = ModuleType("redisvl")`, shadowing installed package.
     - `make test-unit` fails during collection with:
       - `ModuleNotFoundError: No module named 'redisvl.utils'; 'redisvl' is not a package`

2. Evaluation search stack bypasses Qdrant Python SDK and uses raw REST calls.
   - Evidence:
     - `src/evaluation/search_engines.py:12`
     - `src/evaluation/search_engines.py:102`
     - `src/evaluation/search_engines.py:203`
     - `src/evaluation/search_engines.py:331`
     - `src/evaluation/search_engines.py:457`
   - Problem:
     - Direct `requests.post(...)` to `/points/search` and `/points/query` with custom payload serialization.
     - No explicit request timeout.
     - Logic duplicates behavior already covered in SDK-based code (`telegram_bot/services/qdrant.py`).

### P1

3. Multiple parallel custom clients for local embeddings/rerank APIs create drift risk.
   - Evidence:
     - `telegram_bot/integrations/embeddings.py:46`
     - `telegram_bot/services/bge_m3_dense.py:17`
     - `telegram_bot/services/embeddings.py:8`
     - `telegram_bot/services/vectorizers.py:18`
     - `src/ingestion/unified/qdrant_writer.py:111`
   - Problem:
     - Same endpoints (`/encode/dense`, `/encode/sparse`, `/encode/hybrid`, `/rerank`, `/embed*`) are wrapped in multiple places with different timeout/retry policies.
     - Harder to enforce one contract and one failure mode.

4. Docker voice stack has reproducibility and secret hygiene issues in dev profile.
   - Evidence:
     - `docker-compose.dev.yml:699` (`livekit/sip:latest`)
     - `docker-compose.dev.yml:709`
     - `docker-compose.dev.yml:710`
     - `docker-compose.dev.yml:733`
     - `docker-compose.dev.yml:734`
   - Problem:
     - Floating image tag (`latest`) breaks deterministic deployments.
     - Static API credentials (`devkey` / `secret`) are hardcoded.

### P2

5. Runtime Dockerfiles for API/Voice run as root user.
   - Evidence:
     - `src/api/Dockerfile:12`
     - `src/voice/Dockerfile:9`
   - Problem:
     - No non-root user configured in runtime stages (contrast with hardened bot/ingestion images).

## Context7-backed SDK directions

1. Qdrant SDK (`/qdrant/qdrant-client`):
   - Use `client.query_points(...)` with filters/prefetch/fusion patterns instead of manual REST.
   - This removes custom JSON shaping and improves typing + client compatibility.

2. Docling Serve (`/docling-project/docling-serve`):
   - Keep using official API contract (`/v1/convert/file`, `/v1/chunk/hybrid/file/async`) with explicit `convert_*` and `chunking_*` params.
   - Standardize parameter profile mapping in one place.

3. LiveKit (`/websites/livekit_io`):
   - Follow self-hosted SIP configuration patterns and avoid floating tags in compose.
   - Move credentials to env/secrets, not hardcoded values.

## Proposed tasks

### Task A (P0) - Fix unit test contamination
- Update RedisVL test mocks to avoid writing `sys.modules["redisvl"]` when package exists.
- Scope mocks only to `redisvl.query.filter`.
- Verify: `make test-unit` must pass collection and full unit run.

### Task B (P0) - Migrate evaluation search to SDK
- Refactor `src/evaluation/search_engines.py` to `qdrant-client` (`QdrantClient` + `models`) for all search variants.
- Add explicit per-call timeout and consistent error handling.
- Remove environment-specific path hacks:
  - `src/evaluation/search_engines.py:15`

### Task C (P1) - Consolidate local embedding/rerank clients
- Introduce one shared SDK-style module (single source of truth) for:
  - BGE dense/sparse/hybrid
  - ColBERT rerank
  - USER-base embedding
- Replace duplicate wrappers incrementally (bot, ingestion, cache vectorizer paths).

### Task D (P1/P2) - Docker hardening
- Pin `livekit/sip` to explicit version.
- Replace hardcoded LiveKit API credentials with env-required vars.
- Add non-root users for `src/api/Dockerfile` and `src/voice/Dockerfile`.

## Acceptance criteria

1. `make check` and `make test-unit` both pass.
2. `src/evaluation/search_engines.py` has no raw Qdrant REST calls.
3. All local embedding/rerank API calls use one shared client layer.
4. `docker-compose.dev.yml` has no `livekit/sip:latest` and no hardcoded LiveKit API credentials.
5. API and voice runtime images run as non-root.

## Verification notes (this review run)

- `make check`: PASS (ruff + mypy).
- `make test-unit`: FAIL at collection with RedisVL module shadowing error.
