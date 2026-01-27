***REMOVED*** retrieval/

Search engine implementations: baseline, hybrid RRF, ColBERT reranking.

***REMOVED******REMOVED*** Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Exports create_search_engine, SearchResult, rerank_results |
| [search_engines.py](./search_engines.py) | 4 search variants: Baseline, HybridRRF, HybridRRFColBERT, DBSFColBERT |
| [reranker.py](./reranker.py) | Cross-encoder reranking (ms-marco-MiniLM, +10-15% NDCG) |

***REMOVED******REMOVED*** Search Engine Variants

| Engine | Method | Recall@1 | Latency |
|--------|--------|----------|---------|
| `BaselineSearchEngine` | Dense only | 91.3% | ~0.5s |
| `HybridRRFSearchEngine` | Dense + Sparse (RRF) | 92.5% | ~0.7s |
| `HybridRRFColBERTSearchEngine` | Dense + Sparse + ColBERT | 94.0% | ~1.0s |
| `DBSFColBERTSearchEngine` | DBSF + ColBERT | 93.5% | ~0.9s |

***REMOVED******REMOVED*** Usage

```python
from src.retrieval import create_search_engine
from src.config import Settings, SearchEngine

settings = Settings(search_engine=SearchEngine.HYBRID_RRF_COLBERT)
engine = create_search_engine(settings)

results = engine.search(query_embedding, top_k=10)
```

***REMOVED******REMOVED*** Related

- [src/models/](../models/) — BGE-M3 embedding model
- [telegram_bot/services/qdrant.py](../../telegram_bot/services/qdrant.py) — Async Qdrant service
