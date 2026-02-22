---
paths: "src/retrieval/**/*.py"
---

# Search Engine Patterns

Quick reference for `src/retrieval/` sync search engines used in evaluation benchmarks.

**Full retrieval docs (LangGraph, QdrantService, config):** `.claude/rules/features/search-retrieval.md`

## Files

| File | Purpose |
|------|---------|
| `src/retrieval/search_engines.py` | BaseSearchEngine ABC + variants |
| `src/retrieval/reranker.py` | ColBERT reranker (sync) |
| `src/retrieval/__init__.py` | Exports |

## Search Engine Variants

| Engine | Recall@1 | Latency | Use Case |
|--------|----------|---------|---------|
| `HybridRRFColBERTSearchEngine` | 94% | ~1.0s | Default — Dense + Sparse + ColBERT |
| `DBSFColBERTSearchEngine` | 91% | ~0.7s | Low-latency variant |
| `HybridRRFSearchEngine` | 92% | ~0.8s | Dense + Sparse, no ColBERT |
| `BaselineSearchEngine` | 91.3% | ~0.65s | Dense only |

## Qdrant SDK Patterns (Sync)

Used in `src/retrieval/` for evaluation (not production bot path).

```python
from qdrant_client import models
from src.retrieval.search_engines import lexical_weights_to_sparse

# 2-stage: Dense + Sparse → RRF fusion
response = client.query_points(
    collection_name="...",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="bm42", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=top_k,
)

# 3-stage: Dense + Sparse → RRF → ColBERT rerank
response = client.query_points(
    collection_name="...",
    prefetch=[
        models.Prefetch(
            prefetch=[
                models.Prefetch(query=dense_vector, using="dense", limit=100),
                models.Prefetch(query=sparse_vector, using="bm42", limit=100),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
        ),
    ],
    query=colbert_vectors,
    using="colbert",
    limit=top_k,
)
```

## Notes

- These engines use **sync** `QdrantClient` — only for evaluation, not bot path
- Bot path uses `AsyncQdrantClient` in `telegram_bot/services/qdrant.py`
- `lexical_weights_to_sparse()` converts BGE-M3 lexical_weights dict → `models.SparseVector`
