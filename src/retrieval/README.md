# src/retrieval/

Benchmark/evaluation search strategy implementations for vector retrieval.

## Purpose

Keep synchronous retrieval strategies available for benchmarks, experiments, and evaluation. Production runtime retrieval composes `src.adapters.embeddings` with the canonical `src.runtime.services.qdrant.QdrantService` gateway through `src.runtime.retrieval`.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Exports `create_search_engine` and search engine classes |
| [`search_engines.py`](./search_engines.py) | Benchmark/eval-only search variants: Baseline, HybridRRF, HybridRRFColBERT, DBSFColBERT |
| [`search_engine_shared.py`](./search_engine_shared.py) | Shared primitives: sparse vector conversion, result shaping |
| [`reranker.py`](./reranker.py) | Cross-encoder reranking (ms-marco-MiniLM, +10-15% NDCG) |
| [`topic_classifier.py`](./topic_classifier.py) | Lightweight topic/doc-type classification for retrieval tuning |

## Search Engine Variants

| Engine | Method | Typical Latency |
|--------|--------|-----------------|
| `BaselineSearchEngine` | Dense only | ~0.5s |
| `HybridRRFColBERTSearchEngine` | Dense + Sparse + ColBERT rerank | ~1.0s |
| `DBSFColBERTSearchEngine` | DBSF + ColBERT | ~0.9s |

## Entrypoints

| Entrypoint | Role |
|------------|------|
| `src.retrieval.create_search_engine(settings)` | Benchmark/eval factory that returns the configured engine |
| `search_engines.py` engine classes | Direct instantiation for evaluation and testing |

## Boundaries

- Retrieval code is **query-only**. It must not write to Qdrant or modify collections.
- Production runtime retrieval should use `src.runtime.retrieval.RetrievalService`; `src/retrieval/search_engines.py` is benchmark/eval-only.
- **Score shapes and payload fields** are coupled to `src/ingestion/unified/qdrant_writer.py`. If the ingestion payload contract changes, retrieval filters and result parsing may need updates.
- `topic_classifier.py` is advisory only; retrieval must still work when classification returns `None`.

## Related Runtime Services

- **Qdrant** — vector database
- **BGE-M3** — embeddings provider (local REST)
- **Voyage** — alternative embeddings provider

## Focused Checks

```bash
# Unit tests
pytest src/retrieval/

# Type-check
make check

# Evaluation AB test (archived under archive/evaluation/)
# python -m archive.evaluation.run_ab_test --help
```

## See Also

- [`../ingestion/`](../ingestion/) — Chunk production and payload contract
- [`../../telegram_bot/services/qdrant.py`](../../telegram_bot/services/qdrant.py) — Async Qdrant service used by the bot
- [`../../DOCKER.md`](../../DOCKER.md) — Docker orchestration and service dependencies
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../../docs/runbooks/README.md`](../../docs/runbooks/README.md) — Operational troubleshooting
