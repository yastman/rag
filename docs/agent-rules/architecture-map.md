***REMOVED*** Architecture Map

***REMOVED******REMOVED*** System Summary
Contextual RAG platform with hybrid retrieval, reranking, multi-tier caching, ingestion pipelines, Telegram UX, and optional voice workflow.

***REMOVED******REMOVED*** Runtime Surfaces
- Telegram bot pipeline: `telegram_bot/`
- RAG API: `src/api/`
- Voice bot + SIP integration: `src/voice/`
- Retrieval engines and evaluation: `src/retrieval/`, `src/evaluation/`
- Unified ingestion: `src/ingestion/unified/`

***REMOVED******REMOVED*** Main Data Flow
1. Documents are parsed/chunked/embedded during ingestion.
2. Embeddings and payload are written to Qdrant collections.
3. User query enters LangGraph pipeline.
4. Classification and cache checks short-circuit cheap paths.
5. Hybrid retrieval + grading + optional reranking produce evidence.
6. Generation step returns final response and updates caches/traces.

***REMOVED******REMOVED*** Infrastructure Map
- Docker compose profiles support fast local slices (`core`, `bot`, `full`, etc.).
- k3s manifests provide VPS deployment path via overlays.
- Observability uses Langfuse-oriented traces and scores.

***REMOVED******REMOVED*** Directory Responsibilities
- `telegram_bot/graph/` - orchestration graph, nodes, routing.
- `telegram_bot/services/` - retrieval/LLM/helper services.
- `telegram_bot/integrations/` - adapters for cache/embeddings/prompt management.
- `src/ingestion/unified/` - CocoIndex flow, state manager, writers.
- `k8s/` - base resources and overlays for deployment modes.
- `docs/` - operational docs, plans, and archives.

***REMOVED******REMOVED*** Canonical Source Files
- `AGENTS.md`
- `docs/agent-rules/workflow.md`
- `docs/PROJECT_STACK.md`
- `docs/PIPELINE_OVERVIEW.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/agent-rules/infra-and-deploy.md`
