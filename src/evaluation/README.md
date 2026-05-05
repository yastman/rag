# evaluation/

Evaluation, experimentation, and observability tooling for the RAG system.

## Files

| File | Purpose |
|------|---------|
| `evaluator.py` | Unified evaluation interface (precision, recall, MRR, NDCG, latency) |
| `ragas_evaluation.py` | RAGAS quality metrics and nightly evaluation runner |
| `run_ab_test.py` | CLI A/B test runner for search configurations |
| `search_engines.py` | Evaluation search engine implementations (DBSF, ColBERT, hybrid) |
| `search_engines_rerank.py` | Reranking strategies (cross-encoder, MMR) |
| `smoke_test.py` | Post-deployment health checks (Qdrant, collection count, latency) |
| `create_golden_set.py` | Generate ground-truth Q&A pairs for RAGAS |
| `generate_test_queries.py` | Synthetic query generation for specific topics |
| `extract_ground_truth.py` | Extract ground truth from expert annotations |
| `langfuse_integration.py` | Production tracing and span logging |
| `metrics_logger.py` | Legacy metrics logging (superseded by Langfuse) |
| `config_snapshot.py` | Legacy config versioning (superseded by MLflow) |

## Focused checks

```bash
uv run pytest tests/unit/evaluation/ -q
```

## Related

- [`docs/RAG_QUALITY_SCORES.md`](../../docs/RAG_QUALITY_SCORES.md) — Scoring taxonomy
- [`tests/README.md`](../../tests/README.md) — Test tiers and commands
