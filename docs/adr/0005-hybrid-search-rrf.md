# ADR-0005: Hybrid Search (Dense + Sparse RRF) as Default

**Status:** Accepted

**Date:** 2026-02-15

## Context

We needed a retrieval strategy that balances:
- Semantic matching (dense embeddings)
- Keyword matching (sparse embeddings)
- Robust ranking across diverse query types

## Decision

Use **hybrid search with RRF fusion** as the default retrieval method.

### Implementation

```
Query → BGE-M3 → Dense Embedding + Sparse Vector
                              ↓
                    Qdrant hybrid_search_rrf()
                              ↓
                    RRF Fusion: 1/(k+rank_dense) + 1/(k+rank_sparse)
```

### Why RRF Fusion

| Method | Pros | Cons |
|--------|------|------|
| Pure dense | Good semantic | Misses keywords |
| Pure sparse | Good keywords | Misses semantics |
| RRF hybrid | Balances both | Slightly more complex |

RRF is parameter-free (no weight tuning) and robust across query types.

## Consequences

### Positive
- Works well for both keyword and semantic queries
- No weight tuning required
- Handles mixed queries naturally

### Negative
- Slower than single-method (two index scans)
- Sparse index size can be large

## When to Use What

| Query Type | Recommended Method |
|-------------|-------------------|
| Natural language | Hybrid RRF |
| Exact keywords | Sparse only |
| Entity lookup | Dense or sparse |
| Complex multi-aspect | Hybrid RRF |

## Configuration

```python
# Qdrant hybrid search
results = await qdrant.hybrid_search_rrf(
    dense_vector=emb,
    sparse_vector=sparse,
    top_k=20,
)
```

## References

- Qdrant service: `telegram_bot/services/qdrant.py`
- RRF: [CArtE SIGIR 2022](https://arxiv.org/abs/2203.10568)
