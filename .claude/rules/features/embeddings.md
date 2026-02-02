---
paths: "**/embed*.py, **/vector*.py, **/voyage*.py, services/bge-m3-api/**, services/bm42/**, services/user-base/**"
---

# Embeddings

Voyage AI, USER-base, BGE-M3, and BM42 embedding services.

## Purpose

Generate dense and sparse embeddings for semantic search and caching.

## Architecture

```
Document Indexing: Voyage voyage-4-large (1024-dim) + BM42 sparse
Query Embedding:   Voyage voyage-4-lite (1024-dim) + BM42 sparse
Semantic Cache:    USER-base (768-dim, Russian optimized)
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/voyage.py` | 26 | VoyageService class |
| `telegram_bot/services/vectorizers.py` | 18 | UserBaseVectorizer |
| `services/bge-m3-api/app.py` | 41 | BGE-M3 FastAPI endpoints |
| `services/bm42/main.py` | 22 | BM42 FastAPI service |
| `services/user-base/main.py` | 20 | USER-base FastAPI service |

## Embedding Models

| Model | Dim | Use Case | Container |
|-------|-----|----------|-----------|
| voyage-4-large | 1024 | Document indexing | API |
| voyage-4-lite | 1024 | Query embedding | API |
| voyage-context-3 | 1024 | Contextualized chunks | API |
| deepvk/USER-base | 768 | Russian semantic cache | dev-user-base:8003 |
| BGE-M3 | 1024 | Dense + sparse + ColBERT | dev-bge-m3:8000 |
| BM42 | sparse | Keyword matching | dev-bm42:8002 |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `VOYAGE_BATCH_SIZE` | 128 | Texts per API request |
| `MATRYOSHKA_DIMS` | (2048,1024,512,256) | Available dimensions |
| Retry attempts | 6 | With exponential backoff |

## Common Patterns

### VoyageService (recommended)

```python
from telegram_bot.services.voyage import VoyageService

service = VoyageService(
    api_key=api_key,
    model_docs="voyage-4-large",    # For indexing
    model_queries="voyage-4-lite",  # For queries (asymmetric)
    model_rerank="rerank-2.5",
)

# Async (recommended)
query_vec = await service.embed_query("search text")
doc_vecs = await service.embed_documents(["doc1", "doc2"])
results = await service.rerank("query", documents, top_k=5)

# Sync wrappers
query_vec = service.embed_query_sync("search text")
```

### UserBaseVectorizer (Russian cache)

```python
from telegram_bot.services.vectorizers import UserBaseVectorizer

vectorizer = UserBaseVectorizer(base_url="http://localhost:8003")

# Async
embedding = await vectorizer.aembed("двухкомнатная квартира")

# Sync
embedding = vectorizer.embed("двухкомнатная квартира")
```

### BGE-M3 API (hybrid)

```python
import httpx

async with httpx.AsyncClient() as client:
    # Dense only
    resp = await client.post("http://localhost:8000/encode/dense",
        json={"texts": ["text"]})
    dense = resp.json()["dense_vecs"]

    # Sparse only
    resp = await client.post("http://localhost:8000/encode/sparse",
        json={"texts": ["text"]})
    sparse = resp.json()["lexical_weights"]

    # All three (most efficient)
    resp = await client.post("http://localhost:8000/encode/hybrid",
        json={"texts": ["text"]})
    result = resp.json()  # dense_vecs, lexical_weights, colbert_vecs
```

### BM42 sparse

```python
resp = await client.post("http://localhost:8002/embed",
    json={"text": "search query"})
sparse = resp.json()  # {"indices": [...], "values": [...]}
```

## Contextualized Embeddings (voyage-context-3)

Process document chunks together to capture cross-chunk context:

```python
from src.models.contextualized_embedding import ContextualizedEmbeddingService

service = ContextualizedEmbeddingService(
    api_key=api_key,
    output_dimension=1024,  # 2048, 1024, 512, or 256
)

# Embed document chunks together (context-aware)
doc_chunks = [["intro", "body", "conclusion"]]  # Chunks from one doc
result = await service.embed_documents(doc_chunks)
# result.embeddings: one vector per chunk, context-aware

# Embed query (single text)
query_vec = await service.embed_query("search query")
```

**Feature flag:** `use_contextualized_embeddings=true`
**API limits:** 1000 docs, 16K chunks, 32K tokens/doc, 120K total tokens
**Best for:** Legal docs, technical docs (structure matters)

See `docs/CONTEXTUALIZED_EMBEDDINGS.md` for full documentation.

## Asymmetric Retrieval

Documents indexed with `voyage-4-large` (high quality, one-time cost).
Queries embedded with `voyage-4-lite` (fast, cheap, continuous).
Both share embedding space → compatible for search.

## Matryoshka Embeddings

Voyage-4 supports variable dimensions:

```python
# Lower dimensions for faster search
embedding = await service.embed_query(text, output_dimension=512)
```

## Dependencies

| Container | Port | RAM | Purpose |
|-----------|------|-----|---------|
| dev-bge-m3 | 8000 | 4GB | Dense + sparse + ColBERT |
| dev-bm42 | 8002 | 1GB | BM42 sparse |
| dev-user-base | 8003 | 2GB | Russian semantic |

## Testing

```bash
pytest tests/unit/test_voyage_service.py -v
pytest tests/unit/test_vectorizers.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Voyage API 429` | Use CacheService, add delays |
| `Connection refused :8003` | `docker compose up -d user-base` |
| Slow BGE-M3 | Check OMP_NUM_THREADS=4 |

## Development Guide

### Adding new embedding model

1. Create FastAPI service in `services/new-model/`
2. Add Dockerfile with model pre-download
3. Add to `docker-compose.dev.yml`
4. Create client class in `telegram_bot/services/`
5. Add tests
