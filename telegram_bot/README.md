# telegram_bot/

Telegram transport layer and bot orchestration for the contextual RAG system.

## Purpose

Handles Telegram updates (text, voice, callbacks), delegates all retrieval and generation to pipelines, and surfaces answers back to users. Keeps transport concerns separate from domain logic.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`main.py`](./main.py) `main()` | CLI entry point: configures logging, initializes observability, starts the bot runtime class with retry |
| [`bot.py`](./bot.py) `PropertyBot` | Bot lifecycle, handlers, and dispatcher wiring. The class name is legacy; the runtime is domain-adaptable. |
| [`pipelines/graph_compat.py`](./pipelines/graph_compat.py) `build_graph()` | Imperative graph-compat facade (delegates to `src/runtime/pipeline/`) |
| [`agents/rag_pipeline.py`](./agents/rag_pipeline.py) | Agent SDK RAG functions (alternative to full LangGraph) |
| [`pipelines/client.py`](./pipelines/client.py) | Client-direct non-RAG and RAG paths for simple queries |
| [`preflight.py`](./preflight.py) | Startup health checks (Redis, Qdrant, external deps) |

## Boundaries

- **Transport does not absorb retrieval/domain logic.** `bot.py` handlers call into `agents` or `pipelines`; they do not query Qdrant or run LLM prompts directly.
- **Ingestion determinism** is owned by `src/ingestion/`; bot code must not modify collection schemas or manifest identity.

## Related Runtime Services

- **Qdrant** — vector search (collections: documents, domain catalogs, history)
- **Redis** — caching, throttling, user context
- **BGE-M3** — dense + sparse embeddings (local REST API)
- Structured logging — observability (optional)
- **LiveKit** — voice calls (archived; see `archive/voice/`)

## Focused Checks

```bash
# Lint and type-check
make check

# Focused bot/runtime unit tests
uv run pytest tests/unit/graph/test_graph.py tests/unit/pipelines/test_client_pipeline.py tests/unit/test_preflight.py -v

# Service-dependent local preflight helper
make test-bot-health
```

## Directory Guide

| Directory | Concern |
|-----------|---------|
| `agents/` | Agent SDK tools and RAG pipeline functions |
| `dialogs/` | Funnel dialogs and filter extraction UI |
| `integrations/` | Embeddings, cache, prompt manager |
| `middlewares/` | Aiogram middlewares (throttling, errors) |
| `pipelines/` | Client-direct pipeline entrypoints and graph-compat facade |
| `services/` | Bot services (Qdrant, cache, query analysis, response generation) |

## See Also

- [`AGENTS.override.md`](AGENTS.override.md) — Bot-specific scope rules and validation
- [`../DOCKER.md`](../DOCKER.md) — Docker bring-up and service dependencies
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../docs/runbooks/README.md`](../docs/runbooks/README.md) — Operational troubleshooting
- [`../src/retrieval/`](../src/retrieval/) — Search engine implementations
- [`../src/ingestion/`](../src/ingestion/) — Document ingestion pipeline
