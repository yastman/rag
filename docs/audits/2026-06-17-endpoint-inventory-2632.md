# HTTP/API Endpoint Inventory — ARCH-18 (#2632)

**Audit date:** 2026-06-17
**Branch:** `audit/2632-endpoint-inventory`
**Related issues:** #2598 (ARCH-02 voice+RAG-API archive), #2597 (mini-app archive), #2684 (user-base archive)

---

## Summary

After the monolith cleanup (#2598, #2597, #2684), the live codebase has no public-facing
HTTP API surface. The Telegram bot is the only production channel. Two internal
Docker-network services (BGE-M3 and Docling) remain. The user-base service has been
archived per #2684.

---

## Kept Endpoints

### `services/bge-m3-api/app.py` — BGE-M3 Embedding Service

Internal Docker-network service. Port `8000` (dev: `127.0.0.1:8000`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + warm-up status |
| POST | `/encode/dense` | Dense 1024-dim embeddings |
| POST | `/encode/sparse` | Sparse SPLADE embeddings |
| POST | `/encode/colbert` | ColBERT-style token embeddings |
| POST | `/encode/hybrid` | Dense + sparse in one request |

Status: **KEEP** — active internal service, referenced by `src/services/bge_m3_client.py`.

---

### `services/docling/` — Docling Document Parsing Service

Internal Docker-network service. Port `5001` (dev: `127.0.0.1:5001`).
Runs `docling-serve` (Docling CLI serve mode). No Python-managed route file; endpoints
are provided by the `docling-serve` binary.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Healthcheck |
| POST | `/convert` | Document to structured Markdown/JSON |

Status: **KEEP** — active internal service, used by `src/ingestion/docling_client.py`.

---

### `archive/user-base/main.py` — USER2-base Dense Embedding Service (Archived)

Internal Docker-network service. Port `8003` (dev: `127.0.0.1:8003`).
Archived per #2684.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + model-loaded status |
| POST | `/embed` | Single-text dense embedding (768-dim) |
| POST | `/embed_batch` | Batch dense embeddings |

Status: **ARCHIVED** — moved to `archive/user-base/`. Not in Compose, not imported by live code.

---

### Telegram Bot — No Public HTTP

`telegram_bot/` has no FastAPI or HTTP server. `telegram_bot/metrics_server.py` is a
no-op compatibility shim (DEPS-OBS3 removed the in-process Prometheus endpoint).
`telegram_bot/main.py` starts an aiogram polling loop only.

Status: **KEEP** — no HTTP endpoints; correct by design.

---

### Infrastructure Services (Qdrant, Redis, PostgreSQL)

Standard infra. Ports exposed on localhost only in dev overlay (`compose.dev.yml`):

| Service | Dev port | Purpose |
|---------|----------|---------|
| Qdrant HTTP | `6333` | Vector search API |
| Qdrant gRPC | `6334` | gRPC interface |
| Redis | `6379` | Cache and semantic search |
| PostgreSQL | `5432` | App state and ingestion tracking |

Status: **KEEP** — infra only, no app-managed routes.

---

## Archived / Removed Endpoints

### `archive/api/main.py` — RAG FastAPI HTTP API

Archived in `ARCH-02 #2598`. Was `src/api/main.py`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Healthcheck |
| POST | `/query` | RAG query endpoint |

Status: **ARCHIVED** — in `archive/api/`. Not in Compose, not imported by live code.

---

### `archive/mini_app/api.py` — Telegram Mini App Backend

Archived in `#2597`. Was `archive/mini_app/api.py`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config` | Mini-app configuration |
| POST | `/api/start-expert` | Expert mode entry |
| POST | `/api/log` | Event logging |
| POST | `/api/phone` | Phone number collection |
| GET | `/health` | Healthcheck |

Status: **ARCHIVED** — in `archive/mini_app/`. Not in Compose, not imported by live code.

---

### `archive/voice/` — LiveKit Voice Agent

Archived in `ARCH-02 #2598`. No FastAPI routes; LiveKit agent framework manages its own
transport. RAG queries were forwarded to the now-archived RAG API.

Status: **ARCHIVED** — in `archive/voice/`. Not in Compose.

---

## Dead References Removed in This PR

The following test files imported from `src.api.*` or `src.voice.*` (archived in `#2598`)
without skip guards, causing collection errors. No live caller remains — verified by
`grep -r "src\.api\|src\.voice" src/ --include="*.py"` returning no results.

| File | Dead import | Action |
|------|-------------|--------|
| `tests/unit/api/test_rag_api.py` | `src.api.schemas` | Removed |
| `tests/unit/api/test_schemas.py` | `src.api.schemas` | Removed |
| `tests/unit/api/test_rag_api_runtime.py` | `src.api.main`, `src.api.schemas` | Removed |
| `tests/unit/voice/test_rag_api_client.py` | `src.voice.rag_api_client` | Removed |
| `tests/unit/voice/test_voice_healthcheck.py` | `src.voice.healthcheck` | Removed |
| `tests/unit/voice/test_voice_observability.py` | `src.voice.observability` | Removed |
| `tests/unit/voice/test_voice_schemas.py` | `src.voice.schemas` | Removed |
| `tests/unit/voice/test_transcript_store.py` | `src.voice.transcript_store` | Removed |
| `tests/unit/agents/test_voice_agent_factory.py` | `telegram_bot.agents.voice_agent` | Removed |
| `tests/contract/test_voice_agent_factory_contract.py` | `telegram_bot.agents.voice_agent` | Removed |

Additional cleanup:
- `Makefile`: added `test-voice-extra` stub target (required by `test_core_gate_optional_surfaces_contract.py`).
- `.env.example`: removed voice-only dead vars (`LIFECELL_SIP_USER`, `LIFECELL_SIP_PASS`, `DATABASE_URL`, `# ELEVENLABS_VOICE_ID`, `# VOICE_LLM_MODEL`, `# VOICE_DATABASE_URL`, `# LIFECELL_SIP_NUMBER`).

---

## Compose Port Exposure (Current State)

Base `compose.yml` exposes no ports (prod-safe). Dev overlay `compose.dev.yml` exposes
localhost-only ports:

| Service | Port | Proto |
|---------|------|-------|
| bge-m3 | `8000` | HTTP |
| docling | `5001` | HTTP |
| qdrant | `6333`, `6334` | HTTP, gRPC |
| redis | `6379` | Redis |
| postgres | `5432` | Postgres |
| langfuse (ml profile) | `3001` | HTTP |
| clickhouse (ml profile) | `8123`, `9009` | HTTP |
| minio (ml profile) | `9090`, `9091` | HTTP |
| redis-langfuse (ml profile) | `6380` | Redis |
| loki (obs profile) | `3100` | HTTP | **archived #2599** |
| alertmanager (obs profile) | `9093` | HTTP | **archived #2599** |

No `rag-api`, `voice-agent`, `livekit`, or `mini-app` services remain in Compose.

---

## Needs Decision

| Item | Status |
|------|--------|
| `tests/unit/voice/test_sip_setup.py` | Uses `pytest.importorskip("livekit")`; skips cleanly |
| `tests/unit/voice/test_voice_agent.py` | Uses `pytest.importorskip("livekit")`; skips cleanly |
| `tests/contract/test_no_partial_fastapi_shim_contract.py` | Tests that `test_rag_api_runtime.py` uses importorskip; passes trivially after file removal |
| Async-without-await contract failures | Pre-existing (#2617 side-effect); out of scope for this PR |
