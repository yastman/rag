# services/

Bot services for RAG pipeline: embeddings, search, caching, query processing, and response generation.

## Purpose

Pure computation and I/O wrapper modules used by Telegram handlers and the API. No Telegram transport code lives here.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Public API exports (QdrantService, BGEM3Client, GenerationDeps, etc.) |
| [`qdrant.py`](./qdrant.py) | Re-export shim → `src.runtime.qdrant.QdrantService` (the real hybrid dense+sparse+ColBERT gateway) |
| [`generation/telegram_formatting.py`](./generation/telegram_formatting.py) | Telegram-only HTML formatting/delivery for generated answers (generation itself lives in `src/runtime/generation`) |
| [`src/runtime/services/rag_core.py`](../../src/runtime/services/rag_core.py) | Canonical shared RAG core functions |
| [`apartment/filter_extractor.py`](./apartment/filter_extractor.py) | Rule-based filter extraction: price ranges, rooms, city, distance to sea |
| [`apartment/apartment_llm_extractor.py`](./apartment/apartment_llm_extractor.py) | LLM-based apartment data extraction |

## Boundaries

- Services are **stateless** except for Redis-backed caches; they do not own conversation memory (LangGraph checkpointer does).
- **No Telegram transport imports** in this directory. Services receive plain data and return plain data.
- `src/runtime/services/rag_core.py` is the lowest-level shared layer: no observability, no metrics, pure computation.

## Related Runtime Services

- **Qdrant** — vector database queries
- **Redis** — cache tiers and user context storage
- **BGE-M3** — embedding provider
- Prompt management and observability (optional)

## Focused Checks

```bash
# Unit tests for services
pytest telegram_bot/services/

# Type-check
make check
```

## See Also

- [`../AGENTS.override.md`](../AGENTS.override.md) — Bot-specific scope rules and validation
- [`../../DOCKER.md`](../../DOCKER.md) — Docker bring-up and service dependencies
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../../docs/runbooks/README.md`](../../docs/runbooks/README.md) — Operational troubleshooting
- [`../middlewares/`](../middlewares/) — Error handling, throttling, trace root
- [`../../src/retrieval/`](../../src/retrieval/) — Search engine implementations
