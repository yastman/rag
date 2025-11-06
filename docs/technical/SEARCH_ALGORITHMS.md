# Search Algorithms Specification

**Location:** `src/retrieval/search_engines.py`
**Factory:** `create_search_engine()` at line 644

## Engines Comparison

| Engine | Vectors | Fusion | Rerank | Recall@1 | NDCG@10 | Latency | Location |
|--------|---------|--------|--------|----------|---------|---------|----------|
| Baseline | Dense | None | None | 91.3% | 0.9619 | 0.65s | :62-109 |
| HybridRRF | Dense+BM42 | RRF | None | ~90% | ~0.96 | 0.72s | :111-272 |
| RRF+ColBERT | Dense+BM42+ColBERT | RRF | MaxSim | ~95% | ~0.98 | 0.8s | :274-457 |
| DBSF+ColBERT | Dense+Sparse+ColBERT | DBSF | MaxSim | ~94% | ~0.97 | 0.8s | :459-642 |

**Production:** RRF+ColBERT (Variant A)

## 1. Baseline

**Algorithm:**
```
query_vector → dense_search(quantized) → rescore(original) → top_k
```

**Config:**
```python
search_params = {
    "quantization": {
        "rescore": True,
        "oversampling": 3.0
    }
}
```

## 2. Hybrid RRF

**Algorithm:**
```
query → BGE-M3(dense+sparse)
  ├─ dense_search(100)
  ├─ sparse_search(100)
  └─ RRF_fusion → top_k
```

**RRF Formula:**
```
score = Σ 1/(60 + rank_i)
```

**Implementation:** `src/retrieval/search_engines.py:181-268`

```python
prefetch = [
    {"query": dense_emb, "using": "dense", "limit": 100},
    {"query": {"values": [...], "indices": [...]}, "using": "bm42", "limit": 100}
]
query = {"fusion": "rrf"}
```

## 3. Hybrid RRF + ColBERT ✅

**Algorithm:**
```
query → BGE-M3(dense+sparse+colbert)
  ├─ Stage 1: Prefetch
  │   ├─ dense_search(100)
  │   └─ sparse_search(100)
  ├─ Stage 2: RRF fusion → 20 candidates
  └─ Stage 3: ColBERT MaxSim → top_k
```

**MaxSim Formula:**
```
score = Σ max_similarity(q_token, all_d_tokens)
        for q_token in query_tokens
```

**Implementation:** `src/retrieval/search_engines.py:354-453`

```python
prefetch = [{
    "prefetch": [
        {"query": dense_emb, "using": "dense", "limit": 100},
        {"query": sparse_vec, "using": "bm42", "limit": 100}
    ],
    "query": {"fusion": "rrf"}
}]
query = colbert_vecs
using = "colbert"
```

## 4. DBSF + ColBERT

**Algorithm:**
```
Same as #3 but with DBSF fusion instead of RRF
```

**DBSF Formula:**
```
normalized_score = (score - (μ - 3σ)) / 6σ
clamped to [0, 1]
```

**Difference:**
- RRF: Rank-based (ignores scores)
- DBSF: Score-based (statistical normalization)

## Fallback Chain

```
RRF+ColBERT → (fail) → HybridRRF → (fail) → Baseline
```

**Location:** `:421-428, :607-613`

## Configuration

```python
from src.config import SearchEngine
from src.retrieval.search_engines import create_search_engine

engine = create_search_engine(
    engine_type=SearchEngine.HYBRID_RRF_COLBERT
)

results = engine.search(
    query_embedding="text query",  # String for hybrid
    top_k=10,
    score_threshold=0.3
)
```

**Enums:**
- `SearchEngine.BASELINE`
- `SearchEngine.HYBRID_RRF`
- `SearchEngine.HYBRID_RRF_COLBERT` ✅ default
- `SearchEngine.DBSF_COLBERT`

## Performance Tuning

### Prefetch Limits

```python
"limit": 100  # Default
"limit": 200  # Better recall, slower
"limit": 50   # Faster, lower recall
```

### Score Thresholds

- Baseline: 0.5 (high confidence)
- Hybrid: 0.3 (recommended)
- Experimental: 0.1 (very permissive)

### Quantization Oversampling

```python
"oversampling": 3.0  # Baseline only
```

Higher = better accuracy with quantization (slower)

## References

- Implementation: `src/retrieval/search_engines.py`
- Qdrant Hybrid: https://qdrant.tech/articles/hybrid-search/
- BM42: https://qdrant.tech/articles/bm42/
- ColBERT: https://qdrant.tech/documentation/concepts/hybrid-queries/
