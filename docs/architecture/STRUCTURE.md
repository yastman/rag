# Canonical project structure

This map records active module ownership. It describes current directories, not planned packages.

> **Status:** current-state authority. The proposed reusable RAG VPS v2 target is documented in
> [`RAG_VPS_V2_PROPOSED.md`](RAG_VPS_V2_PROPOSED.md) and must not be read as already implemented.

## Assistant path

| Path | Ownership |
|---|---|
| `src/core` | Public transport-free assistant entrypoint, contracts, dependency wiring, and telemetry |
| `src/runtime` | RAG orchestration, retrieval, grounding, generation, graph construction, and runtime integrations |
| `src/runtime/pipeline` | Procedural classify, cache, retrieve, grade/rerank, rewrite, and generate stages |
| `src/adapters` | Provider adapters for embeddings and LLMs |
| `src/ingestion` | Document loading, chunking, and collection writes |
| `src/ingestion/unified` | Unified ingestion command path |
| `src/retrieval` | Retrieval-facing classification helpers outside runtime orchestration |
| `telegram_bot` | Telegram transport, handlers, and process assembly |
| `services/bge-m3-api` | BGE-M3 embedding sidecar |

## Dependency direction

`src/core` is the public boundary and delegates execution to `src/runtime`. Transport packages may call the core or runtime APIs, but runtime code must not import `telegram_bot`.

`src/adapters` supplies integrations below orchestration and must not acquire new imports from `src/runtime`. `src/ingestion` is parallel infrastructure: it owns writes and must not import runtime orchestration. Runtime retrieval is query-only.

When an active directory moves or ownership changes, update this map and the canonical structure contracts in the same change.
