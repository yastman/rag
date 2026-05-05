# telegram_bot/

Telegram transport layer and bot orchestration for the contextual RAG system.

## Purpose

Handles Telegram updates (text, voice, callbacks), delegates all retrieval and generation to pipelines, and surfaces answers back to users. Keeps transport concerns separate from domain logic.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`main.py`](./main.py) `main()` | CLI entry point: configures logging, initializes Langfuse, starts `PropertyBot` with retry |
| [`bot.py`](./bot.py) `PropertyBot` | Bot lifecycle, handlers, and dispatcher wiring |
| [`graph/graph.py`](./graph/graph.py) `build_graph()` | LangGraph RAG pipeline assembly (cache → rewrite → retrieve → grade → respond) |
| [`agents/rag_pipeline.py`](./agents/rag_pipeline.py) | Agent SDK RAG functions (alternative to full LangGraph) |
| [`pipelines/client.py`](./pipelines/client.py) | Client-direct non-RAG and RAG paths for simple queries |
| [`preflight.py`](./preflight.py) | Startup health checks (Redis, Qdrant, Langfuse) |

## Boundaries

- **Transport does not absorb retrieval/domain logic.** `bot.py` handlers call into `graph`, `agents`, or `pipelines/client`; they do not query Qdrant or run LLM prompts directly.
- **LangGraph state contracts** (`graph/state.py`) must be preserved when adding new nodes or edges.
- **Ingestion determinism** is owned by `src/ingestion/`; bot code must not modify collection schemas or manifest identity.

## Related Runtime Services

- **Qdrant** — vector search (collections: documents, apartments, history)
- **Redis** — caching, throttling, user context
- **BGE-M3** — dense + sparse embeddings (local REST API)
- **Langfuse** — tracing and observability (optional, graceful degradation)
- **LiveKit** — voice calls (see `src/voice/`; deferred by default)

## Focused Checks

```bash
# Lint and type-check
make check

# Unit tests for graph state and pipeline logic
pytest telegram_bot/graph/state_contract.py telegram_bot/pipelines/

# Preflight smoke test
python -m telegram_bot.preflight
```

## Directory Guide

| Directory | Concern |
|-----------|---------|
| `agents/` | Agent SDK tools and RAG pipeline functions |
| `dialogs/` | Funnel dialogs and filter extraction UI |
| `graph/` | LangGraph runtime: nodes, edges, state, context |
| `integrations/` | Langfuse, embeddings, cache, prompt manager |
| `middlewares/` | Aiogram middlewares (throttling, errors, Langfuse trace root) |
| `pipelines/` | Client-direct pipeline entrypoints |
| `services/` | Bot services (Qdrant, cache, query analysis, response generation) |

## See Also

- [`../DOCKER.md`](../DOCKER.md) — Docker bring-up and service dependencies
- [`../src/retrieval/`](../src/retrieval/) — Search engine implementations
- [`../src/ingestion/`](../src/ingestion/) — Document ingestion pipeline
