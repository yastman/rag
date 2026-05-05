# src/

Shared domain, retrieval, ingestion, and API code for the contextual RAG system.

## Purpose

Contains all non-transport logic: document ingestion, vector search, model contextualization, evaluation, and the standalone RAG API. `telegram_bot/` imports from here; most of `src/` stays Telegram-agnostic. `src/api/` is an adapter that intentionally reuses the Telegram LangGraph pipeline (via `telegram_bot.graph.graph.build_graph()`) until that pipeline is extracted into a shared location.

## Entrypoints

| Surface | Entrypoint | Role |
|---------|------------|------|
| Ingestion (legacy) | `src.ingestion.service` | High-level ingestion service wrapper |
| Ingestion (current) | `src.ingestion.unified.cli` | CocoIndex-based unified pipeline CLI |
| Retrieval | `src.retrieval.create_search_engine` | Factory for search engine variants |
| API | `src.api.main:app` | FastAPI application for HTTP RAG queries |
| Voice | `src.voice.agent` | LiveKit voice agent (deferred) |
| Evaluation | `src.evaluation.smoke_test` | Smoke tests and RAG quality evaluation |

## Directory Guide

| Directory | Concern |
|-----------|---------|
| `api/` | FastAPI RAG API — thin wrapper around LangGraph pipeline |
| `config/` | Shared settings, constants, and Qdrant collection policy |
| `contextualization/` | Claude-based contextualized embedding generation |
| `core/` | Legacy RAG pipeline orchestrator |
| `evaluation/` | Smoke tests, RAGAS, AB tests, Langfuse integration |
| `governance/` | Compliance and policy helpers |
| `ingestion/` | Document parsing, chunking, indexing, unified pipeline |
| `models/` | BGE-M3 contextualized embedding model wrappers |
| `retrieval/` | Search engines (baseline, hybrid RRF, DBSF+ColBERT) |
| `security/` | Security utilities |
| `utils/` | Shared helpers |
| `voice/` | LiveKit voice agent and SIP setup (deferred by default) |

## Boundaries

- **`src/` must not depend on `telegram_bot/`**. All Telegram-specific code lives in `telegram_bot/`.
- **Ingestion determinism and resumability** are owned by `src/ingestion/` and `src/ingestion/unified/`. Do not change manifest identity, hashing, or collection semantics without careful review.
- **LangGraph state contracts** are defined in `telegram_bot/graph/state.py`; `src/api/` reuses the same pipeline but does not redefine state shapes.

## Related Runtime Services

- **Qdrant** — vector database (used by retrieval, ingestion, and history)
- **PostgreSQL** — CocoIndex state for unified ingestion
- **Redis** — caching and rate limiting (used indirectly via `telegram_bot/` services)
- **BGE-M3 / Voyage** — embedding providers
- **Docling** — document parsing
- **Langfuse** — tracing and evaluation (optional)
- **LiveKit** — voice infrastructure (deferred/off by default)

## Focused Checks

```bash
make check
pytest src/retrieval/ src/ingestion/unified/ src/api/
```

## See Also

- [`../telegram_bot/README.md`](../telegram_bot/README.md) — Telegram transport layer
- [`../DOCKER.md`](../DOCKER.md) — Docker orchestration and service dependencies
