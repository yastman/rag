# services/

Bot services for RAG pipeline: embeddings, search, caching, query processing.

## Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Public API exports (VoyageService, CacheService, QdrantService, etc.) |
| [voyage.py](./voyage.py) | Voyage AI unified gateway: embeddings (voyage-4-large/lite) + reranking (rerank-2.5) |
| [cache.py](./cache.py) | Multi-level cache: semantic LLM answers, embeddings, search results, rerank, conversation |
| [qdrant.py](./qdrant.py) | Qdrant smart gateway: RRF fusion, score boosting, MMR diversity, binary quantization |
| [query_preprocessor.py](./query_preprocessor.py) | Rule-based preprocessing: translit normalization (Latin→Cyrillic), dynamic RRF weights |
| [query_router.py](./query_router.py) | Query classification (CHITCHAT/SIMPLE/COMPLEX) to skip RAG for greetings |
| [cesc.py](./cesc.py) | Context-Enabled Semantic Cache personalizer with lazy routing |
| [llm.py](./llm.py) | LLM answer generation (OpenAI-compatible) with streaming and fallback |
| [retriever.py](./retriever.py) | Dense vector search in Qdrant with dynamic filters |
| [query_analyzer.py](./query_analyzer.py) | LLM-based filter extraction (price, city, rooms) from natural language |
| [user_context.py](./user_context.py) | User preferences extraction via LLM, stored in Redis with 30-day TTL |
| [embeddings.py](./embeddings.py) | BGE-M3 embedding service via HTTP API (legacy, prefer VoyageService) |
| [filter_extractor.py](./filter_extractor.py) | Rule-based filter extraction: price ranges, rooms, city, distance to sea |

## Related

- [telegram_bot/middlewares/](../middlewares/) — Error handling, throttling
- [src/retrieval/](../../src/retrieval/) — Search engine implementations
- [CLAUDE.md](../../CLAUDE.md) — Architecture overview
