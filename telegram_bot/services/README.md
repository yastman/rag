# services/

Bot services for RAG pipeline: embeddings, search, caching, query processing, and response generation.

## Purpose

Pure computation and I/O wrapper modules used by Telegram handlers and the API. No Telegram transport code lives here.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Public API exports (VoyageService, CacheService, QdrantService, etc.) |
| [`voyage.py`](./voyage.py) | Voyage AI gateway: embeddings + reranking |
| [`qdrant.py`](./qdrant.py) | Async Qdrant gateway: hybrid search, RRF, ColBERT, binary quantization |
| [`query_preprocessor.py`](./query_preprocessor.py) | Rule-based preprocessing: translit normalization, dynamic RRF weights |
| [`query_analyzer.py`](./query_analyzer.py) | LLM-based filter extraction (price, city, rooms) from natural language |
| [`generate_response.py`](./generate_response.py) | Canonical response generation with Langfuse prompt management |
| [`rag_core.py`](./rag_core.py) | Shared RAG core functions (no Langfuse spans, no metrics) |
| [`llm.py`](./llm.py) | LLM answer generation with streaming and fallback |
| [`filter_extractor.py`](./filter_extractor.py) | Rule-based filter extraction: price ranges, rooms, city, distance to sea |
| [`apartment_llm_extractor.py`](./apartment_llm_extractor.py) | LLM-based apartment data extraction |
| [`ingestion_cocoindex.py`](./ingestion_cocoindex.py) | Thin wrapper around `src.ingestion.service` for bot-side ingestion commands |

## Boundaries

- Services are **stateless** except for Redis-backed caches; they do not own conversation memory (LangGraph checkpointer does).
- **No Telegram transport imports** in this directory. Services receive plain data and return plain data.
- `rag_core.py` is the lowest-level shared layer: no observability, no metrics, pure computation.

## Related Runtime Services

- **Qdrant** — vector database queries
- **Redis** — cache tiers and user context storage
- **BGE-M3 / Voyage** — embedding providers
- **Langfuse** — prompt management and observability (optional)

## Focused Checks

```bash
# Unit tests for services
pytest telegram_bot/services/

# Type-check
make check
```

## See Also

- [`../middlewares/`](../middlewares/) — Error handling, throttling, Langfuse trace root
- [`../../src/retrieval/`](../../src/retrieval/) — Search engine implementations
