---
paths: "src/retrieval/**, **/qdrant*.py, **/retriever*.py"
---

# Search & Retrieval

Hybrid search with RRF fusion, Qdrant vector database, and reranking.

## Purpose

Retrieve relevant documents using combination of dense (semantic) and sparse (keyword) vectors with intelligent fusion and reranking.

## Architecture

```
Query → Dense Embedding (Voyage) + Sparse Embedding (BM42)
     → Qdrant Prefetch (dense + sparse)
     → RRF Fusion
     → [Optional] Voyage Rerank
     → Results
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `src/retrieval/search_engines.py` | 56 | BaseSearchEngine ABC |
| `src/retrieval/search_engines.py` | 78 | BaselineSearchEngine |
| `telegram_bot/services/qdrant.py` | 19 | QdrantService (async) |
| `telegram_bot/services/retriever.py` | 12 | RetrieverService (sync, legacy) |

## Search Engine Variants

| Engine | Recall@1 | Latency | Description |
|--------|----------|---------|-------------|
| HybridRRFColBERT | 94% | ~1.0s | Dense + Sparse + ColBERT (default) |
| DBSFColBERT | 91% | ~0.7s | 7% faster variant |
| HybridRRF | 92% | ~0.8s | Without ColBERT |
| Baseline | 91.3% | ~0.65s | Dense only |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dense_weight` | 0.6 | RRF weight for dense vectors |
| `sparse_weight` | 0.4 | RRF weight for sparse vectors |
| `prefetch_multiplier` | 3 | Overfetch ratio for RRF |
| `use_quantization` | true | Enable Binary Quantization |

## RRF Weights by Query Type

| Query Type | Dense | Sparse | Example |
|------------|-------|--------|---------|
| Semantic | 0.6 | 0.4 | "уютная квартира с видом" |
| Exact | 0.2 | 0.8 | "корпус 5", "ID 12345" |

## Common Patterns

### Hybrid search with RRF

```python
from telegram_bot.services.qdrant import QdrantService

qdrant = QdrantService(
    url="http://localhost:6333",
    collection_name="contextual_bulgaria_voyage",
)

results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,      # From VoyageService
    sparse_vector=sparse_embedding,    # From BM42
    filters={"city": "Несебр"},
    top_k=10,
    dense_weight=0.6,
    sparse_weight=0.4,
)
```

### Qdrant SDK nested prefetch (sync)

```python
from qdrant_client import models

response = client.query_points(
    collection_name="documents",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="bm42", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=top_k,
)
```

### Score boosting (freshness)

```python
results = await qdrant.search_with_score_boosting(
    dense_vector=query_embedding,
    freshness_boost=True,
    freshness_field="created_at",
    freshness_scale_days=7,
)
```

### MMR diversity reranking

```python
diverse_results = qdrant.mmr_rerank(
    points=results,
    embeddings=result_embeddings,
    lambda_mult=0.5,  # 0=diversity, 1=relevance
    top_k=5,
)
```

## Filter Building

```python
# Exact match
filters = {"city": "Несебр"}

# Range filter
filters = {"price": {"gte": 50000, "lte": 100000}}

# Combined
filters = {
    "city": "Бургас",
    "rooms": 2,
    "price": {"lt": 80000}
}
```

## Binary Quantization

Enabled by default for 40x faster search, 75% less RAM:

```python
# Disable for A/B testing
results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    quantization_ignore=True,  # Use full vectors
)
```

## Dependencies

- Container: `dev-qdrant` (6333, 6334 gRPC)
- Collections: `contextual_bulgaria_voyage`, `legal_documents`

## Testing

```bash
pytest tests/unit/test_qdrant_service.py -v
pytest tests/unit/test_search_engines.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Qdrant timeout` | Enable `use_quantization=True` |
| Low recall | Check embedding model matches collection |
| Empty results | Verify collection name, check filters |

## Development Guide

### Adding new search engine

1. Create class in `src/retrieval/search_engines.py`
2. Inherit from `BaseSearchEngine`
3. Implement `search()` and `get_name()` methods
4. Add to `SearchEngine` enum in `src/config/settings.py`
5. Write benchmark in `src/evaluation/`
