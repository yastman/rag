# src/

Shared domain, retrieval, ingestion, and runtime engine code for the RAG system.

## Purpose

Contains all non-transport logic: the public boundary (`core/`), the shared runtime engine
(`runtime/`), document ingestion, retrieval, model contextualization, and embedding/LLM
adapters. `telegram_bot/` imports from here; `src/` stays Telegram-agnostic. The runtime
kernel lives in `src/runtime/` and does not import `telegram_bot.*`.

## Entrypoints

| Surface | Entrypoint | Role |
|---------|------------|------|
| Public boundary | `src.core.assistant.run_assistant_request` | Single entrypoint used by all adapters + the golden E2E |
| RAG engine | `src.runtime.pipeline.rag.rag_pipeline` | cache → hybrid search → grade → rerank → optional rewrite |
| Ingestion | `src.ingestion.unified.cli` | Unified ingestion pipeline CLI |

## Directory Guide

| Directory | Concern |
|-----------|---------|
| `adapters/` | Embedding + LLM provider adapters (BGE-M3, OpenAI, LiteLLM) |
| `config/` | Shared settings, constants, and Qdrant collection policy |
| `contextualization/` | LLM-based contextualized embedding generation (Claude / OpenAI / Groq) |
| `core/` | Public boundary: Protocol DI contracts (`contracts.py`) + `assistant.py` entrypoint |
| `ingestion/` | Document parsing, chunking, indexing, unified pipeline |
| `models/` | Embedding model singletons + domain models |
| `observability/` | Structured-logging helpers + no-op `@observe` shim (Langfuse removed) |
| `retrieval/` | Reranking + topic classification (benchmark/eval strategies) |
| `runtime/` | Shared runtime engine: graph, pipeline, generation, qdrant, retrieval, grounding, llm |
| `security/` | PII redaction and security utilities |
| `services/` | Shared service clients (BGE-M3, Voyage, Kommo, handoff state) |
| `utils/` | Shared helpers |

## Boundaries

- **`src/` stays Telegram-agnostic.** The runtime kernel lives in `src/runtime/` and imports nothing from `telegram_bot.*` (ratchet: `tests/contract/test_layering_no_telegram_bot_imports_contract.py`).
- **Ingestion determinism and resumability** are owned by `src/ingestion/` and `src/ingestion/unified/`. Do not change manifest identity, hashing, or collection semantics without careful review.
- **Graph state contracts** live in `src/runtime/graph/state.py`; adapters reuse the same pipeline and do not redefine state shapes.

## Related Runtime Services

- **Qdrant** — vector database (retrieval, ingestion, history)
- **PostgreSQL** — domain state (users, leads, funnel, favorites)
- **Redis** — caching and rate limiting
- **BGE-M3 / Voyage** — embedding providers
- **Docling** — in-process document parsing (native SDK)
- Structured logging — observability

## Focused Checks

```bash
make check
pytest src/ingestion/unified/
```

## See Also

- [`../telegram_bot/README.md`](../telegram_bot/README.md) — Telegram transport layer
- [`../DOCKER.md`](../DOCKER.md) — Docker orchestration and service dependencies
- [`../docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../docs/runbooks/README.md`](../docs/runbooks/README.md) — Operational troubleshooting
