# HTTP/ASGI Endpoint Surface Inventory — #2709

**Audit date:** 2026-06-17
**Branch:** `arch/2709`
**Related issues:** #2632 (ARCH-18 prior inventory), #2694 (src/voice + src/api), #2696 (stale test/script leftovers), #2704 (BGE-M3 consolidation)

---

## Summary

After the monolith cleanup (#2598, #2597), there is **no public-facing HTTP API surface**.
The Telegram bot is the only production channel.  Two internal Docker-network services
(BGE-M3 and Docling) are active.  All other previously described endpoints are archived.

---

## Full Inventory

| Surface | Endpoint | Owner file | Caller(s) | Tests | Status | Action |
|---------|----------|------------|-----------|-------|--------|--------|
| BGE-M3 | `GET /health` | `services/bge-m3-api/app.py` | `telegram_bot/preflight.py`, `scripts/index_contextual_api.py` | `tests/unit/test_bge_m3_rerank.py`, smoke tests | **KEEP** — core internal | None |
| BGE-M3 | `POST /encode/dense` | `services/bge-m3-api/app.py` | `src/services/bge_m3_client.py` | `tests/unit/services/test_bge_m3_client.py`, `tests/smoke/test_ingestion_health.py` | **KEEP** — core internal | None |
| BGE-M3 | `POST /encode/sparse` | `services/bge-m3-api/app.py` | `src/services/bge_m3_client.py` | `tests/smoke/test_ingestion_health.py` | **KEEP** — core internal | None |
| BGE-M3 | `POST /encode/colbert` | `services/bge-m3-api/app.py` | `src/services/bge_m3_client.py` | `tests/unit/test_bge_m3_rerank.py` | **KEEP** — core internal | None |
| BGE-M3 | `POST /encode/hybrid` | `services/bge-m3-api/app.py` | `src/services/bge_m3_client.py` | `tests/smoke/test_ingestion_health.py`, `tests/smoke/test_smoke_bge_litellm_cache.py` | **KEEP** — core internal | None |
| BGE-M3 | `POST /rerank` | `services/bge-m3-api/app.py` | `src/runtime/services/colbert_reranker.py`, `src/services/bge_m3_client.py` | `tests/unit/test_colbert_reranker.py`, `tests/unit/services/test_bge_m3_client.py` | **KEEP** — core internal | None |
| Docling | `GET /health` | `docling-serve` binary | `src/ingestion/unified/cli.py`, `src/ingestion/docling_client.py` | `tests/smoke/test_smoke_services.py` | **KEEP** — core internal (ingestion profile) | None |
| Docling | `POST /v1/chunk/hybrid/file` | `docling-serve` binary | `src/ingestion/docling_client.py` | `tests/unit/ingestion/test_unified_cli.py` | **KEEP** — core internal (ingestion profile) | None |
| Qdrant HTTP | `*` (vector API) | Qdrant container | `src/retrieval/`, ingestion pipeline | `tests/smoke/test_ingestion_health.py` | **KEEP** — infra only | None |
| Redis | `*` (protocol) | Redis container | `src/runtime/integrations/cache.py` | unit + smoke | **KEEP** — infra only | None |
| PostgreSQL | `*` (protocol) | Postgres container | ORM / session state | integration | **KEEP** — infra only | None |
| Telegram bot | n/a (no HTTP) | `telegram_bot/main.py` | aiogram polling, no HTTP | unit + integration | **KEEP** — no HTTP endpoints | None |
| RAG API `GET /health` | archived | `archive/api/main.py` | none (archived) | `tests/e2e/test_core_flows_live.py` (legacy_api mark) | **ARCHIVED** — #2598 | ✅ test marked legacy_api (#2709) |
| RAG API `POST /query` | archived | `archive/api/main.py` | `archive/voice/rag_api_client.py`, `scripts/archive/run_experiment_langfuse_sdk.py` | `tests/e2e/test_core_flows_live.py` (legacy_api), `tests/integration/test_voice_pipeline.py` (requires_services skip) | **ARCHIVED** — #2598 | ✅ scripts archived, test marked (#2709) |
| Mini App `GET /api/config` | archived | `archive/mini_app/api.py` | none | none | **ARCHIVED** — #2597 | None needed |
| Mini App `POST /api/start-expert` | archived | `archive/mini_app/api.py` | none | none | **ARCHIVED** — #2597 | None needed |
| Mini App `POST /api/log` | archived | `archive/mini_app/api.py` | none | none | **ARCHIVED** — #2597 | None needed |
| Mini App `POST /api/phone` | archived | `archive/mini_app/api.py` | none | none | **ARCHIVED** — #2597 | None needed |
| Mini App `GET /health` | archived | `archive/mini_app/api.py` | none | none | **ARCHIVED** — #2597 | None needed |
| Voice agent (LiveKit) | archived | `archive/voice/agent.py` | none | `tests/integration/test_voice_pipeline.py` (requires_services skip) | **ARCHIVED** — #2598 | None needed (skip guard present) |
| user-base `GET /health` | archived | `archive/user-base/main.py` | none | none | **ARCHIVED** — moved from `services/` (#2627) | None needed |
| user-base `POST /embed` | archived | `archive/user-base/main.py` | none | none | **ARCHIVED** — #2627 | None needed |
| user-base `POST /embed_batch` | archived | `archive/user-base/main.py` | none | none | **ARCHIVED** — #2627 | None needed |

---

## Compose Port Exposure (Current State)

Base `compose.yml` exposes no ports (prod-safe).  Dev overlay `compose.dev.yml` exposes
localhost-only ports:

| Service | Dev port | Proto | Status |
|---------|----------|-------|--------|
| bge-m3 | `8000` | HTTP | **Active** |
| docling | `5001` | HTTP | **Active** (ingestion profile) |
| qdrant | `6333`, `6334` | HTTP, gRPC | **Active** |
| redis | `6379` | Redis | **Active** |
| postgres | `5432` | Postgres | **Active** |
| langfuse (ml profile) | `3001` | HTTP | Optional |
| clickhouse (ml profile) | `8123`, `9009` | HTTP | Optional |
| minio (ml profile) | `9090`, `9091` | HTTP | Optional |
| redis-langfuse (ml profile) | `6380` | Redis | Optional |
| loki (obs profile) | `3100` | HTTP | Optional |
| alertmanager (obs profile) | `9093` | HTTP | Optional |

No `rag-api`, `voice-agent`, `livekit`, `mini-app`, or `user-base` services remain in Compose.

---

## Stale References Cleaned in This PR (#2709)

| Location | Stale reference | Fix |
|----------|----------------|-----|
| `DOCKER.md` line 46 | voice profile listed as "Optional surface; off by default" | Updated to "Archived surface; removed from Compose (#2598)" |
| `docs/LOCAL-DEVELOPMENT.md` | `uv run uvicorn src.api.main:app` command | Commented out as archived |
| `docs/LOCAL-DEVELOPMENT.md` | `user-base` in VPS runtime service list | Removed |
| `docs/PIPELINE_OVERVIEW.md` §4 | Voice flow pointing at `src/voice/agent.py` + `src/api/main.py` | Updated to archived notice |
| `docs/observability/CROSS_SERVICE_TRACING.md` | `services/user-base/main.py`, `src/api/main.py`, `mini_app/api.py` in active table | Updated to `archive/*` paths |
| `docs/observability/TRACE_COVERAGE_AUDIT_2168.md` | `rag-api-query → src/api/main.py:326` | Updated to `archive/api/main.py` (archived) |
| `docs/RAG_QUALITY_SCORES.md` | `src/api/main.py` in scoring hook description | Updated to `archive/api/main.py` |
| `docs/RAG_QUALITY_SCORES.md` | `rag-api-query` and `voice-session` in required trace families | Updated with archived note |
| `docs/runbooks/EMBEDDING_SERVICE_FAILURE.md` | `user-base` in service/container map and alert query | Removed |
| `scripts/run_experiment.py` | Active script calling archived RAG API `POST /query` | Moved to `scripts/archive/run_experiment_langfuse_sdk.py` |
| `Makefile` `eval-sdk-experiment*` targets | Called archived `scripts/run_experiment.py` | Removed |
| `scripts/README.md` | `run_experiment.py` listed under active Experiment scripts | Updated |
| `tests/unit/test_run_experiment.py` | Imported from archived `scripts/run_experiment.py` | Deleted |
| `tests/e2e/test_core_flows_live.py` | pytestmark missing `legacy_api` | Added `pytest.mark.legacy_api` |

---

## Needs Decision (Out of Scope for This PR)

| Item | Tracking issue |
|------|---------------|
| `src/voice/` + `src/api/` still under `src/` (zero core imports) | #2694 |
| `src/evaluation/` under `src/` (zero core imports, ARCH-09 archived) | #2694 |
| BGE-M3 endpoint handler / client consolidation | #2704 |
| `tests/integration/test_voice_pipeline.py` — targets archived LiveKit + RAG API but has skip guards | #2696 |
| Archive linter excludes (`archive/` not yet excluded from ruff/bandit) | #2694 |
