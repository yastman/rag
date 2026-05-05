***REMOVED*** src/retrieval/

Search engine implementations for vector retrieval.

***REMOVED******REMOVED*** Purpose

Execute hybrid and dense vector searches against Qdrant, with optional reranking. Consumes chunks produced by `src/ingestion/`.

***REMOVED******REMOVED*** Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Exports `create_search_engine`, `SearchResult`, `rerank_results` |
| [`search_engines.py`](./search_engines.py) | 4 search variants: Baseline, HybridRRF, HybridRRFColBERT, DBSFColBERT |
| [`search_engine_shared.py`](./search_engine_shared.py) | Shared primitives: sparse vector conversion, result shaping |
| [`reranker.py`](./reranker.py) | Cross-encoder reranking (ms-marco-MiniLM, +10-15% NDCG) |
| [`topic_classifier.py`](./topic_classifier.py) | Lightweight topic/doc-type classification for retrieval tuning |

***REMOVED******REMOVED*** Search Engine Variants

| Engine | Method | Typical Latency |
|--------|--------|-----------------|
| `BaselineSearchEngine` | Dense only | ~0.5s |
| `HybridRRFSearchEngine` | Dense + Sparse (RRF) | ~0.7s |
| `HybridRRFColBERTSearchEngine` | Dense + Sparse + ColBERT rerank | ~1.0s |
| `DBSFColBERTSearchEngine` | DBSF + ColBERT | ~0.9s |

***REMOVED******REMOVED*** Entrypoints

| Entrypoint | Role |
|------------|------|
| `src.retrieval.create_search_engine(settings)` | Factory that returns the configured engine |
| `search_engines.py` engine classes | Direct instantiation for evaluation and testing |

***REMOVED******REMOVED*** Boundaries

- Retrieval code is **query-only**. It must not write to Qdrant or modify collections.
- **Score shapes and payload fields** are coupled to `src/ingestion/unified/qdrant_writer.py`. If the ingestion payload contract changes, retrieval filters and result parsing may need updates.
- `topic_classifier.py` is advisory only; retrieval must still work when classification returns `None`.

***REMOVED******REMOVED*** Related Runtime Services

- **Qdrant** — vector database
- **BGE-M3** — embeddings provider (local REST)
- **Voyage** — alternative embeddings provider

***REMOVED******REMOVED*** Focused Checks

```bash
***REMOVED*** Unit tests
pytest src/retrieval/

***REMOVED*** Type-check
make check

***REMOVED*** Evaluation AB test (heavy, requires populated collection)
python -m src.evaluation.run_ab_test --help
```

***REMOVED******REMOVED*** See Also

- [`../ingestion/`](../ingestion/) — Chunk production and payload contract
- [`../../telegram_bot/services/qdrant.py`](../../telegram_bot/services/qdrant.py) — Async Qdrant service used by the bot
