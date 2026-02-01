---
paths: "src/retrieval/**/*.py"
---

# Search Engine Patterns

Qdrant hybrid search with RRF fusion.

## Search Engine Variants

- **HybridRRFColBERTSearchEngine** (default): Dense + Sparse + ColBERT rerank. Recall@1: 0.94, ~1.0s latency
- **DBSFColBERTSearchEngine**: 7% faster variant for low-latency requirements
- **HybridRRFSearchEngine**: Dense + Sparse without ColBERT
- **BaselineSearchEngine**: Dense only (91.3% Recall@1)

#***REMOVED*** SDK Patterns

All hybrid engines use Qdrant SDK `query_points()` with nested prefetch (no httpx):

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
