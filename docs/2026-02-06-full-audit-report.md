# Full Audit Report (Code + Docker)

Date: 2026-02-06
Project: `/opt/rag-fresh`
Auditor: Codex (GPT-5)

## Scope

- Code review: `src/`, `telegram_bot/`, `scripts/`, `Makefile`
- Docker review: `Dockerfile*`, `services/*/Dockerfile`, `docker-compose*.yml`
- Runtime verification: active `vps-*` containers
- Official SDK docs cross-check via Context7:
  - `/qdrant/qdrant-client`
  - `/redis/redis-vl-python`
  - `/langfuse/langfuse-python`

## Executive Summary

- Total findings: 12
- Critical: 2
- High: 4
- Medium: 4
- Low/Info: 2

Most important issues are in ingestion reliability and operational consistency: non-persistent GDrive state, broken `make ingest-gdrive` path, config drift in confidence threshold, and Redis eviction sampling mismatch in VPS.

## Findings

| ID | Severity | Area | Evidence | Impact | Recommendation |
|---|---|---|---|---|---|
| F-01 | Critical | Ingestion (GDrive watcher) | `src/ingestion/gdrive_flow.py:4`, `src/ingestion/gdrive_flow.py:118`, `src/ingestion/gdrive_flow.py:120`, `src/ingestion/gdrive_flow.py:252` | Code claims persistent sqlite state but uses only in-memory `self._processed`. After restart, change detection/deletion reconciliation loses history. | Implement real persistent state (sqlite/postgres) or update logic/docs to match actual behavior. |
| F-02 | Critical | Ingestion CLI / Make | `Makefile:661`, `Makefile:666`, `telegram_bot/services/ingestion_cocoindex.py:93`, `src/ingestion/service.py:211` | `make ingest-gdrive` routes to code path explicitly marked "not yet implemented". Command is functionally broken for users. | Repoint `make ingest-gdrive` to `src.ingestion.gdrive_flow` (or implement CocoIndex GDrive path). |
| F-03 | High | Ingestion defaults / collection routing | `src/ingestion/service.py:59`, `src/ingestion/service.py:261`, `telegram_bot/services/ingestion_cocoindex.py:50`, `Makefile:669` | Default collection is `documents`, while runtime bot uses `gdrive_documents_bge`; status/ingest commands can target wrong collection silently. | Align defaults with environment (`QDRANT_COLLECTION`/`GDRIVE_COLLECTION_NAME`) and expose explicit collection flag in Make targets. |
| F-04 | High | Guardrails confidence logic | `telegram_bot/config.py:114`, `telegram_bot/services/llm.py:17`, `telegram_bot/services/llm.py:262`, `telegram_bot/bot.py:130` | Runtime threshold is hardcoded `0.5`, config exposes `LOW_CONFIDENCE_THRESHOLD=0.3`, but value is never passed into `LLMService`. Behavior differs from expected ops config. | Inject threshold into `LLMService` constructor and remove hardcoded constant drift. |
| F-05 | High | Redis runtime policy (VPS) | `docker-compose.vps.yml:42`; runtime check `redis-cli CONFIG GET maxmemory-samples -> 5` | Plan expects `maxmemory-samples=10`, but VPS runs with default 5, reducing LFU/LRU stability under memory pressure. | Add `--maxmemory-samples 10` in VPS redis command and validate via preflight. |
| F-06 | Medium | Redis policy (local compose) | `docker-compose.local.yml:27` | Local stack still uses `allkeys-lfu`, inconsistent with safer volatile policy expected by cache/index separation. | Switch local compose to `volatile-lfu` and add `--maxmemory-samples 10` for parity. |
| F-07 | Medium | Preflight portability | `Makefile:234`, `Makefile:240`, `Makefile:246`, `Makefile:266` | `test-redis`/`test-bot-health` are hardwired for `dev-*` stack and localhost assumptions. They fail in current `vps-*` runtime. | Parameterize container/service names and endpoints via env vars (`REDIS_CONTAINER`, `QDRANT_URL`, `LLM_BASE_URL`). |
| F-08 | Medium | Observability (Langfuse) | `docker-compose.vps.yml:220` (bot env block has no `LANGFUSE_*`); runtime log: `vps-bot` warning "initialized without public_key" | Langfuse client in bot becomes disabled/no-op in VPS, so tracing and score observability are lost. | Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` to VPS bot env when observability is required. |
| F-09 | Medium | Docker image hardening | `Dockerfile:1`, `Dockerfile:6`, `Dockerfile:12`, `Dockerfile:15` | Root image is legacy single-stage (`gcc` in runtime, `pip install`, `COPY . .`), larger attack surface and slower builds compared to current optimized service images. | Migrate root Dockerfile to multi-stage + uv cache pattern, add healthcheck and slimmer runtime. |
| F-10 | Low | Docker portability | `services/bm42/Dockerfile:53`, `services/user-base/Dockerfile:53`, `services/bge-m3-api/Dockerfile:65` | Service images rely on compose-level healthchecks only; image-level self-health absent if run outside compose. | Add lightweight `HEALTHCHECK` in each image for standalone reliability. |
| F-11 | Low | Config contract drift | `src/config/settings.py` (no `retrieval_profile`), plan contract expects profile-based switch | Documented profile contract (`fast/balanced/quality`) is not implemented in central settings. | Implement `retrieval_profile` mapping or remove completed status from plan/docs. |
| F-12 | Info | ACORN status drift | Runtime check in `vps-bot`: `AcornSearchParams_exists True` with `qdrant-client 1.16.2`; `docs/plans/2026-02-01-rag-2026-tz.md:599` still says SDK-blocked | Docs/plans claim ACORN blocked by SDK, but installed SDK supports `AcornSearchParams`. | Update plan status from "blocked" to "available in current SDK", then re-enable benchmark/rollout decision. |

## Context7 Notes (Official SDK)

1. Qdrant Python client (`/qdrant/qdrant-client`)
- Official docs show filtered vector search and `SearchParams` usage patterns.
- Local runtime confirms `AcornSearchParams` is present in installed SDK (`qdrant-client 1.16.2`), so old "SDK blocked" assumption is stale.

2. RedisVL (`/redis/redis-vl-python`)
- Official examples initialize `SemanticCache`/`EmbeddingsCache` with `redis_url` (constructor-level URL).
- This explains why "single shared redis client pool across RedisVL + raw redis-py" is non-trivial and needs explicit architectural handling.

3. Langfuse Python SDK (`/langfuse/langfuse-python`)
- Official SDK initialization requires `public_key` + `secret_key` (or corresponding env vars).
- Missing keys lead to no-op/disabled behavior, matching observed VPS bot warning.

Context7 source URLs used:
- Qdrant client docs: `https://github.com/qdrant/qdrant-client/blob/master/docs/source/index.rst`
- RedisVL SemanticCache docs: `https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/03_llmcache.ipynb`
- RedisVL EmbeddingsCache docs: `https://github.com/redis/redis-vl-python/blob/main/docs/user_guide/10_embeddings_cache.ipynb`
- Langfuse Python SDK docs index (Context7): `/langfuse/langfuse-python`

## Runtime Snapshot (checked 2026-02-06 UTC)

- Redis (`vps-redis`):
  - `maxmemory-policy = volatile-lfu`
  - `maxmemory-samples = 5` (expected by project plan: 10)
- Qdrant (`vps-qdrant`):
  - collections: `gdrive_documents_bge`
  - `contextual_bulgaria_voyage*` absent in current runtime
- Bot (`vps-bot`):
  - starts healthy and polling
  - Langfuse disabled due missing public key in env

## Priority Fix Plan

1. Fix ingestion correctness first:
- Implement persistent state in `src/ingestion/gdrive_flow.py`.
- Fix `make ingest-gdrive` path to working pipeline.

2. Fix behavior/config drift:
- Wire `LOW_CONFIDENCE_THRESHOLD` into `LLMService`.
- Align ingestion default collections with runtime env.

3. Fix ops consistency:
- Set VPS redis `maxmemory-samples=10`.
- Unify local/vps Redis eviction policy.
- Parameterize preflight commands for `dev-*` and `vps-*`.

4. Fix observability and docs:
- Add Langfuse env to VPS bot if tracing is required.
- Update stale plan statuses (ACORN blocked, completed flags mismatching code).
