# Docker SDK Map

Use this index when a task starts from a Docker service name and you need the
project SDK/framework guidance before editing code, runtime config, or docs.

`DOCKER.md` remains the source of truth for Compose files, profiles, service
names, ports, env vars, and health checks. This page only maps services to the
local SDK docs, runbooks, and Context7 refresh targets agents should use.

## Lookup Policy

1. Start with the service row below.
2. Read the linked local docs and the matching section in
   [`../engineering/sdk-registry.md`](../engineering/sdk-registry.md).
3. Check current code/config paths named by those docs.
4. Use Context7 or official docs only when local docs are missing, stale, or the
   task depends on version-sensitive behavior.
5. If Context7 was required, capture the useful project-specific result locally
   before finishing:
   - `sdk-registry.md` for short SDK rules, gotchas, or new `context7_id`
   - a subsystem README or reference doc for project recipes and examples
   - `docs/runbooks/*.md` for incident diagnosis or operational recovery
   - this page when a Docker service gains or loses SDK/doc ownership

## Service Map

| Docker service | Primary local docs | SDK/framework docs | Context7 refresh target | Update when Context7 adds |
|---|---|---|---|---|
| `postgres` | [`../../DOCKER.md`](../../DOCKER.md), [`../runbooks/POSTGRESQL_WAL_RECOVERY.md`](../runbooks/POSTGRESQL_WAL_RECOVERY.md) | `asyncpg` in [`../engineering/sdk-registry.md`](../engineering/sdk-registry.md) | `/MagicStack/asyncpg`; official PostgreSQL/pgvector docs for container/runtime behavior | Pooling, migration, WAL, or pgvector rules |
| `redis` | [`observability-and-storage.md`](observability-and-storage.md), [`../runbooks/REDIS_CACHE_DEGRADATION.md`](../runbooks/REDIS_CACHE_DEGRADATION.md), [`../TROUBLESHOOTING_CACHE.md`](../TROUBLESHOOTING_CACHE.md) | `redis-py (asyncio)`, `redisvl` | `/redis/redis-py`, `/redis/redis-vl-python`; official Redis docs for server config | Cache, TTL, pub/sub, eviction, or semantic-cache rules |
| `qdrant` | [`observability-and-storage.md`](observability-and-storage.md), [`../QDRANT_STACK.md`](../QDRANT_STACK.md), [`../runbooks/QDRANT_TROUBLESHOOTING.md`](../runbooks/QDRANT_TROUBLESHOOTING.md) | `qdrant-client` | `/qdrant/qdrant-client`; official Qdrant docs for server config | Query API, collection schema, filter, RRF, or ColBERT rules |
| `bge-m3` | [`runtime-services.md`](runtime-services.md), [`../../services/README.md`](../../services/README.md), [`../adr/0002-bge-m3-embeddings.md`](../adr/0002-bge-m3-embeddings.md) | BGE-M3 service client paths via local code; Qdrant/RedisVL docs for consumers | Context7 or official FlagEmbedding/Hugging Face docs when model API changes | Embedding output contract, dense/sparse/ColBERT shape, cache compatibility |
| `user-base` | [`runtime-services.md`](runtime-services.md), [`../../services/README.md`](../../services/README.md) | Sentence-transformers service usage in local code | Official sentence-transformers/Hugging Face docs when model API changes | Model loading, cache, or embedding contract changes |
| `docling` | [`runtime-services.md`](runtime-services.md), [`../INGESTION.md`](../INGESTION.md), [`../../src/ingestion/README.md`](../../src/ingestion/README.md) | `docling` | `/docling-project/docling` | Parser backend, table mode, PDF/DOCX, or chunk contract rules |
| `litellm` | [`observability-and-storage.md`](observability-and-storage.md), [`../runbooks/LITEllm_FAILURE.md`](../runbooks/LITEllm_FAILURE.md), [`../../docker/README.md`](../../docker/README.md) | OpenAI-compatible client path through LiteLLM, Langfuse callbacks | Official LiteLLM docs; `/openai/openai-python` for client-side use | Proxy routing, fallback, retry, callback, or OpenAI-compatible behavior |
| `bot` | [`runtime-services.md`](runtime-services.md), [`../../telegram_bot/README.md`](../../telegram_bot/README.md), [`../BOT_ARCHITECTURE.md`](../BOT_ARCHITECTURE.md) | `aiogram`, `aiogram-dialog`, `langgraph`, `qdrant-client`, `redisvl`, `redis-py`, `langfuse`, `instructor`, `openai` | Matching `context7_id` sections in `sdk-registry.md` | Handler/dialog, graph, cache, retrieval, tracing, or extraction rules |
| `mini-app-api` | [`runtime-services.md`](runtime-services.md), [`../../mini_app/README.md`](../../mini_app/README.md) | `fastapi`, `redis-py`, `langfuse` | `/fastapi/fastapi`, `/redis/redis-py`, `/langfuse/langfuse-python` | API route, deep-link state, pub/sub, or trace rules |
| `mini-app-frontend` | [`runtime-services.md`](runtime-services.md), [`../../mini_app/README.md`](../../mini_app/README.md) | `@telegram-apps/sdk` / TMA SDK entry in `sdk-registry.md` | `/telegram-mini-apps/tma.js`; official Vite/React docs only for frontend build changes | Telegram Mini App init, theme, viewport, or swipe behavior |
| `ingestion` | [`runtime-services.md`](runtime-services.md), [`../INGESTION.md`](../INGESTION.md), [`../../src/ingestion/unified/README.md`](../../src/ingestion/unified/README.md) | `cocoindex`, `docling`, `qdrant-client`, `asyncpg`, `langfuse` | `/cocoindex-io/cocoindex`, `/docling-project/docling`, `/qdrant/qdrant-client`, `/MagicStack/asyncpg`, `/langfuse/langfuse-python` | Flow builder, parser, target connector, state, or tracing rules |
| `clickhouse` | [`runtime-services.md`](runtime-services.md), [`observability-and-storage.md`](observability-and-storage.md), [`../../DOCKER.md`](../../DOCKER.md) | Langfuse self-host dependency, not app SDK-owned | Official Langfuse self-host and ClickHouse docs | Langfuse storage, migration, retention, or health rules |
| `minio` | [`runtime-services.md`](runtime-services.md), [`../../DOCKER.md`](../../DOCKER.md) | Langfuse self-host object storage, not app SDK-owned | Official Langfuse self-host and MinIO/S3 docs | Langfuse upload/media/event storage rules |
| `redis-langfuse` | [`runtime-services.md`](runtime-services.md), [`observability-and-storage.md`](observability-and-storage.md) | Langfuse self-host Redis, separate from app `redis` | Official Langfuse self-host and Redis docs | Langfuse queue/cache rules |
| `langfuse-worker` | [`observability-and-storage.md`](observability-and-storage.md), [`../runbooks/LANGFUSE_TRACING_GAPS.md`](../runbooks/LANGFUSE_TRACING_GAPS.md) | `langfuse` for app instrumentation; self-host docs for worker runtime | `/langfuse/langfuse-python`; official Langfuse self-host docs | Worker, queue, OTEL, or ingestion rules |
| `langfuse` | [`observability-and-storage.md`](observability-and-storage.md), [`../RAG_QUALITY_SCORES.md`](../RAG_QUALITY_SCORES.md), [`../runbooks/LANGFUSE_TRACING_GAPS.md`](../runbooks/LANGFUSE_TRACING_GAPS.md) | `langfuse` | `/langfuse/langfuse-python`; official Langfuse self-host docs | Trace, observation, score, prompt, or self-host rules |
| `loki` | [`runtime-services.md`](runtime-services.md), [`../ALERTING.md`](../ALERTING.md) | Runtime service; no app SDK owner | Official Loki docs | Log query, retention, or readiness rules |
| `promtail` | [`runtime-services.md`](runtime-services.md), [`../ALERTING.md`](../ALERTING.md) | Runtime service; no app SDK owner | Official Promtail/Grafana Agent docs | Log shipping, scrape, or label rules |
| `alertmanager` | [`runtime-services.md`](runtime-services.md), [`../ALERTING.md`](../ALERTING.md) | Runtime service; no app SDK owner | Official Alertmanager docs | Routing, receiver, or silence rules |
| `rag-api` | [`runtime-services.md`](runtime-services.md), [`../RAG_API.md`](../RAG_API.md), [`../../src/api/README.md`](../../src/api/README.md) | `fastapi`, `openai`, `langfuse`, `qdrant-client`, `redis-py` | `/fastapi/fastapi`, `/openai/openai-python`, `/langfuse/langfuse-python`, `/qdrant/qdrant-client`, `/redis/redis-py` | Route, client, tracing, retrieval, or cache rules |
| `livekit-server` | [`runtime-services.md`](runtime-services.md), [`../../src/voice/README.md`](../../src/voice/README.md) | LiveKit runtime backing `livekit-agents` | `/livekit/agents`; official LiveKit server docs | Room, token, WebRTC, or server config rules |
| `livekit-sip` | [`runtime-services.md`](runtime-services.md), [`../../src/voice/README.md`](../../src/voice/README.md) | LiveKit SIP runtime backing voice path | `/livekit/agents`; official LiveKit SIP docs | Trunk, dispatch, SIP URI, or media routing rules |
| `voice-agent` | [`runtime-services.md`](runtime-services.md), [`../../src/voice/README.md`](../../src/voice/README.md) | `livekit-agents`, `openai`, `langfuse` | `/livekit/agents`, `/openai/openai-python`, `/langfuse/langfuse-python` | Agent session, STT/TTS, tool, RAG API, or tracing rules |

## Refresh Notes

- Keep Compose service names, profiles, ports, env vars, and health checks in
  [`../../DOCKER.md`](../../DOCKER.md), not here.
- Keep SDK rules in [`../engineering/sdk-registry.md`](../engineering/sdk-registry.md).
- Keep incident workflows in [`../runbooks/README.md`](../runbooks/README.md) and
  focused runbooks.
- When a Docker image or dependency is upgraded, review only the rows for the
  affected services and update `Context7 refresh target` or local docs if the
  project pattern changed.
