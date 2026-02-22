---
paths: "**/embed*.py, **/vector*.py, **/voyage*.py, services/bge-m3-api/**, services/bm42/**, services/user-base/**, **/integrations/embeddings.py"
---

# Embeddings

BGE-M3, Voyage AI, USER-base, and BM42 embedding services + LangChain wrappers.

## Purpose

Generate dense and sparse embeddings for semantic search and caching.

## Architecture

```
VPS Production:
  Dense + Sparse: BGE-M3 (1024-dim dense + lexical sparse, single CPU service)
  Rerank:         ColBERT MaxSim (via BGE-M3 /rerank, timeout=120s, graceful degradation)
  Semantic Cache:  USER-base (768-dim, Russian optimized)

Dev:
  Dense:  Voyage voyage-4-large (indexing, Matryoshka: 2048/1024/512/256-dim) / voyage-4-lite (queries)
  Rerank: rerank-2.5 (32K context)
  Sparse: BM42 (deprecated on VPS, replaced by BGE-M3 /encode/sparse)
  Cache:  USER-base (768-dim)

LangGraph Pipeline (via integrations/embeddings.py):
  BGEM3HybridEmbeddings (dense+sparse in 1 call, shared httpx.AsyncClient)
  BGEM3Embeddings (dense only, LangChain Embeddings) — legacy
  BGEM3SparseEmbeddings (sparse only, custom wrapper) — legacy
```

## Key Files

| File | Description |
|------|-------------|
| `telegram_bot/services/bge_m3_client.py` | **BGEM3Client** (async) + **BGEM3SyncClient** — unified SDK for all BGE-M3 API endpoints |
| `telegram_bot/integrations/embeddings.py` | BGEM3HybridEmbeddings (uses BGEM3Client) + legacy wrappers |
| `telegram_bot/services/voyage.py` | VoyageService class |
| `telegram_bot/services/vectorizers.py` | UserBaseVectorizer + BgeM3CacheVectorizer (uses BGEM3Client) |
| `telegram_bot/services/colbert_reranker.py` | ColbertRerankerService (uses BGEM3Client) |
| `services/bge-m3-api/app.py` | BGE-M3 FastAPI endpoints |
| `services/user-base/main.py` | USER-base FastAPI service |

## LangChain Wrappers (LangGraph integration)

### BGEM3HybridEmbeddings (preferred — single API call)

```python
from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

emb = BGEM3HybridEmbeddings(base_url="http://bge-m3:8000", timeout=120.0)
# Shared httpx.AsyncClient with connection pooling (reused across calls)

# Returns (dense, sparse) tuple in one /encode/hybrid call
dense, sparse = await emb.aembed_hybrid("search text")    # (list[float], dict)

# Returns (dense, sparse, colbert) 3-tuple (#569)
dense, sparse, colbert = await emb.aembed_hybrid_with_colbert("search text")
# colbert: list[list[float]] — multi-vector for Qdrant MaxSim rescore

# Also works as LangChain Embeddings (dense only)
vector = await emb.aembed_query("search text")             # list[float], 1024-dim
```

### BGEM3Embeddings (dense) — legacy, use BGEM3HybridEmbeddings instead

```python
from telegram_bot.integrations.embeddings import BGEM3Embeddings

emb = BGEM3Embeddings(base_url="http://bge-m3:8000", timeout=120.0)

# Async (used by cache_check_node)
vector = await emb.aembed_query("search text")            # list[float], 1024-dim
vectors = await emb.aembed_documents(["doc1", "doc2"])     # list[list[float]]

# Sync (for non-async code)
vector = emb.embed_query("search text")
```

Wraps BGE-M3 `/encode/dense` endpoint (fixed from legacy `/encode`). Batching via `batch_size=32`.

### BGEM3SparseEmbeddings (sparse) — legacy, use BGEM3HybridEmbeddings instead

```python
from telegram_bot.integrations.embeddings import BGEM3SparseEmbeddings

sparse = BGEM3SparseEmbeddings(base_url="http://bge-m3:8000")

# Async (used by retrieve_node)
sv = await sparse.aembed_query("search text")      # dict with sparse vector
svs = await sparse.aembed_documents(["d1", "d2"])   # list[dict]
```

Wraps BGE-M3 `/encode/sparse` endpoint (fixed from legacy `/encode`). Returns `lexical_weights` format.

## Embedding Models

| Model | Dim | Use Case | Container |
|-------|-----|----------|-----------|
| BGE-M3 | 1024 | Dense + sparse + ColBERT | dev-bge-m3:8000 |
| voyage-4-large | 1024 | Document indexing | API |
| voyage-4-lite | 1024 | Query embedding | API |
| deepvk/USER-base | 768 | Russian semantic cache | dev-user-base:8003 |
| BM42 | sparse | Keyword matching (DEPRECATED on VPS) | dev-bm42:8002 |

## BGE-M3 API Endpoints

| Endpoint | Returns | Used By |
|----------|---------|---------|
| `/encode/dense` | `dense_vecs` | BGEM3Embeddings |
| `/encode/sparse` | `lexical_weights` | BGEM3SparseEmbeddings |
| `/encode/hybrid` | `dense_vecs` + `lexical_weights` (+ optional `colbert_vecs`) | BGEM3HybridEmbeddings (preferred) |
| `/encode/colbert` | `colbert_vecs` | BGEM3Client.encode_colbert() (#569) |
| `/rerank` | ColBERT scores | ColbertRerankerService (CPU fallback) |

## Dependencies

| Container | Port | RAM | Purpose |
|-----------|------|-----|---------|
| dev-bge-m3 | 8000 | 4GB | Dense + sparse + ColBERT |
| dev-bm42 | 8002 | 1GB | BM42 sparse (deprecated) |
| dev-user-base | 8003 | 2GB | Russian semantic |

## Testing

```bash
pytest tests/unit/test_voyage_service.py -v
pytest tests/unit/test_vectorizers.py -v
pytest tests/unit/integrations/test_embeddings.py -v  # LangChain wrappers
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Voyage API 429` | Use CacheLayerManager, add delays |
| `Connection refused :8003` | `docker compose up -d user-base` |
| Slow BGE-M3 | Check OMP_NUM_THREADS=4 |

## Development Guide

### Adding new embedding model

1. Create FastAPI service in `services/new-model/`
2. Add Dockerfile with model pre-download
3. Add to `docker-compose.dev.yml`
4. Create LangChain wrapper in `telegram_bot/integrations/embeddings.py`
5. Add tests
