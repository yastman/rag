---
paths: "telegram_bot/services/**/*.py"
---

# Service Patterns

Code patterns for telegram_bot/services.

## VoyageService (Recommended)

```python
from telegram_bot.services import VoyageService

# Unified service for embeddings + reranking
service = VoyageService(
    api_key="...",
    model_docs="voyage-4-large",     # For document indexing (1024-dim)
    model_queries="voyage-4-lite",   # For queries (asymmetric retrieval)
    model_rerank="rerank-2.5",       # 32K context window
)

# Async methods (recommended)
query_vec = await service.embed_query("search text")
doc_vecs = await service.embed_documents(["doc1", "doc2"])
results = await service.rerank("query", documents, top_k=5)

# Sync wrappers (for non-async code)
query_vec = service.embed_query_sync("search text")
```

## Local Russian Embeddings (UserBaseVectorizer)

```python
from telegram_bot.services import UserBaseVectorizer

# For semantic cache with Russian text optimization
vectorizer = UserBaseVectorizer(
    base_url="http://localhost:8003",  # or http://user-base:8000 in Docker
)

# Async (recommended)
embedding = await vectorizer.aembed("двухкомнатная квартира")

# Sync wrapper
embedding = vectorizer.embed("двухкомнатная квартира")
```

**Environment:** Set `USE_LOCAL_EMBEDDINGS=true` to use USER-base instead of Voyage API for semantic cache.

## Cache Key Versioning

Cache keys include `CACHE_SCHEMA_VERSION` to prevent pollution when models change:

```python
from telegram_bot.services.cache import CACHE_SCHEMA_VERSION  # "v2"

# Cache key patterns:
# sem:v2:{vectorizer_id}  - SemanticCache (e.g., sem:v2:voyage1024)
# emb:v2                   - EmbeddingsCache
# search:v2:{index_ver}    - Search results
# analysis:v2              - QueryAnalyzer
# rerank:v2                - Rerank results
# sparse:v2:{model}        - Sparse embeddings
```

Bump version when changing models. Old keys expire naturally (TTL 2h-7d).

## Query Preprocessing (QueryPreprocessor)

```python
from telegram_bot.services import QueryPreprocessor
pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5")
# Returns:
# {
#   "normalized_query": "apartments in Солнечный берег корпус 5",  # Translit
#   "rrf_weights": {"dense": 0.2, "sparse": 0.8},  # Exact query -> favor sparse
#   "cache_threshold": 0.05,  # Strict for queries with IDs
#   "is_exact": True
# }
```

- **Semantic queries** (no IDs): RRF weights 0.6/0.4 (dense favored), cache threshold 0.10
- **Exact queries** (IDs, corpus, floors): RRF weights 0.2/0.8 (sparse favored), cache threshold 0.05

## Query Routing (2026 Best Practice)

```python
from telegram_bot.services import classify_query, QueryType, get_chitchat_response

query_type = classify_query("Привет!")  # Returns QueryType.CHITCHAT
if query_type == QueryType.CHITCHAT:
    response = get_chitchat_response(query)  # Skip RAG entirely

# QueryType.SIMPLE  → Light RAG, skip rerank
# QueryType.COMPLEX → Full RAG + rerank
```

## Qdrant Binary Quantization (2026 Best Practice)

```python
from telegram_bot.services import QdrantService

# QdrantService with quantization (default: enabled)
qdrant = QdrantService(
    url="http://localhost:6333",
    collection_name="documents",
    use_quantization=True,           # 40x faster search
    quantization_rescore=True,       # Maintain accuracy
    quantization_oversampling=2.0,   # Fetch 2x candidates, rescore top_k
)

# A/B testing: disable quantization per-request
results_baseline = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    quantization_ignore=True,  # Skip quantization for this request
)
```

## 2026 Performance Defaults

| Parameter          | Value | Purpose                             |
| ------------------ | ----- | ----------------------------------- |
| `search_top_k`     | 20    | Fewer candidates → faster Qdrant    |
| `use_quantization` | true  | 40x faster, 75% less RAM            |
| `rerank_top_k`     | 3     | Fewer chunks in LLM context         |
| `max_tokens`       | 1024  | Faster generation                   |
| Rerank cache TTL   | 2h    | Skip API calls for repeated queries |

## I/O Patterns

- **Telegram Bot services**: Async (`httpx.AsyncClient`, `AsyncQdrantClient`)
- **Search Engines**: Sync Qdrant SDK (`QdrantClient.query_points()`) with `models.Prefetch` for nested prefetch
- No blocking calls in async context for bot handlers

## Legacy

```python
# Legacy BGE-M3 (local model, high RAM)
from src.models.embedding_model import get_bge_m3_model
model = get_bge_m3_model()  # Reuses single instance, saves 4-6GB RAM
```
