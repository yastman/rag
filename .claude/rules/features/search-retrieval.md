---
paths: "src/retrieval/**, **/qdrant*.py, **/retriever*.py"
---

# Search & Retrieval

Hybrid search with RRF fusion, Qdrant vector database, and reranking.

## Purpose

Retrieve relevant documents using combination of dense (semantic) and sparse (keyword) vectors with intelligent fusion and reranking.

## Architecture

```
Query → Dense Embedding (BGE-M3) + Sparse Embedding (BGE-M3)
     → Qdrant Prefetch (dense + sparse)
     → RRF Fusion
     → [Optional] ColBERT Rerank
     → Results

VPS:  BGE-M3 for dense + sparse + ColBERT rerank (local CPU)
Dev:  Voyage dense + BM42 sparse + Voyage rerank (API)
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
| `quantization_mode` | binary | off/scalar/binary (32x compression) |
| `quantization_rescore` | true | Rescore with full vectors |
| `quantization_oversampling` | 2.0 | Fetch 2x more candidates |
| `small_to_big_mode` | off | off/on/auto (context expansion) |
| `small_to_big_window_before` | 1 | Chunks before hit |
| `small_to_big_window_after` | 1 | Chunks after hit |
| `acorn_mode` | off | off/on/auto (filtered search optimization) |
| `acorn_max_selectivity` | 0.4 | Max filter selectivity for ACORN |

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
    dense_vector=query_embedding,      # From BGE-M3 (VPS) or VoyageService (dev)
    sparse_vector=sparse_embedding,    # From BGE-M3 sparse (VPS) or BM42 (dev)
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
        models.Prefetch(query=sparse_vector, using="bm42", limit=100),  # field name "bm42" kept, data from BGE-M3 sparse on VPS
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

**Collection selection:** `settings.get_collection_name()` appends `_binary` or `_scalar` suffix based on mode.

## Small-to-Big Expansion

Fetches neighboring chunks after retrieval for more context:

```python
from telegram_bot.services.small_to_big import SmallToBigService

s2b = SmallToBigService(qdrant_service, settings)
expanded = await s2b.expand_results(
    results=search_results,
    window_before=1,  # 1 chunk before each hit
    window_after=1,   # 1 chunk after each hit
)
```

**Modes:** `off` (disabled), `on` (always expand), `auto` (expand for COMPLEX queries only)

## ACORN (Filtered Search Optimization)

ACORN improves search quality when strict filters cause HNSW graph disconnection. Best for low selectivity filters (< 40% of vectors match).

**Status (Feb 2026):**
| Component | Version | ACORN Support |
|-----------|---------|---------------|
| Qdrant Server | 1.16+ | ✅ Supported |
| qdrant-client (Python) | 1.16.2 | ⚠️ `AcornSearchParams` not yet exported |

Code is ready — will auto-enable when SDK adds the class:
```python
# src/retrieval/search_engines.py
try:
    from qdrant_client.models import AcornSearchParams
    ACORN_AVAILABLE = True
except ImportError:
    ACORN_AVAILABLE = False  # Current state
```

```python
# Auto mode: ACORN enabled only with filters + low selectivity
results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    filters={"city": "Несебр"},  # Triggers ACORN in auto mode
    acorn_mode="auto",
)
```

**Modes:** `off` (disabled), `on` (always use), `auto` (use when beneficial)

**To enable when SDK updates:**
```bash
uv lock --upgrade-package qdrant-client
pytest tests/unit/test_acorn.py -v  # Should show 22 passed (not 8 skipped)
```

## Dependencies

- Container: `dev-qdrant` / `vps-qdrant` (6333, 6334 gRPC)
- Collections: `gdrive_documents_bge` (VPS), `contextual_bulgaria_voyage` (dev), `legal_documents` (dev)

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
