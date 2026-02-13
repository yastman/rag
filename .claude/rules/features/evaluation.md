---
paths: "src/evaluation/**, telegram_bot/evaluation/**, tests/baseline/**, scripts/evaluate_judge.py"
---

# Evaluation & Experiments

Search metrics, RAGAS, MLflow, A/B testing, and LLM-as-a-Judge.

## Purpose

Measure search quality, track experiments, and detect regressions.

## Architecture

```
Queries + Ground Truth → SearchEvaluator → Metrics
                      → MLflow logging → Experiment tracking
                      → Langfuse comparison → Regression detection
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `src/evaluation/evaluator.py` | 20 | SearchEvaluator class |
| `src/evaluation/ragas_evaluation.py` | - | RAGAS integration |
| `src/evaluation/mlflow_integration.py` | - | MLflow setup |
| `src/evaluation/run_ab_test.py` | - | A/B test runner |
| `tests/baseline/collector.py` | - | LangfuseMetricsCollector |
| `tests/baseline/thresholds.yaml` | - | Regression thresholds (incl. judge quality) |
| `telegram_bot/evaluation/judges.py` | - | LLM-as-a-Judge evaluators (RAG Triad) |
| `telegram_bot/evaluation/prompts.py` | - | Judge prompts (faithfulness, relevance, context) |
| `telegram_bot/evaluation/runner.py` | - | Batch runner + online sampling |
| `scripts/evaluate_judge.py` | - | CLI entry point for batch judge |

## Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Recall@1 | Correct in top-1 | >90% |
| Recall@5 | Correct in top-5 | >95% |
| NDCG@10 | Ranking quality | >0.95 |
| MRR | Mean Reciprocal Rank | >0.90 |
| Precision@K | Relevant in top-K | varies |

## Regression Thresholds

From `tests/baseline/thresholds.yaml`:

| Metric | Threshold | Alert if |
|--------|-----------|----------|
| LLM p95 latency | +20% | Latency increases |
| Total cost | +10% | Cost increases |
| Cache hit rate | -10% | Cache less effective |
| LLM calls | +5% | More calls needed |

## Common Patterns

### Evaluate search engine

```python
from src.evaluation.evaluator import SearchEvaluator

evaluator = SearchEvaluator("ground_truth_articles.json")

metrics = evaluator.evaluate_query(
    query={"query": "статья 185", "expected_article": "185"},
    search_results=results,
    k_values=[1, 3, 5, 10],
)
# {"recall@1": 1, "ndcg@10": 0.98, "mrr": 1.0, ...}
```

### Run A/B test

```bash
python src/evaluation/run_ab_test.py \
    --engine-a HybridRRF \
    --engine-b HybridRRFColBERT \
    --queries test_queries.json
```

### Compare baselines

```bash
make baseline-compare \
    BASELINE_TAG=smoke-abc-20260128 \
    CURRENT_TAG=smoke-def-20260202
```

### Set new baseline

```bash
make baseline-set TAG=smoke-def-20260202
```

## MLflow Tracking

```python
import mlflow

with mlflow.start_run(run_name="hybrid_rrf_v2"):
    mlflow.log_param("search_engine", "HybridRRFColBERT")
    mlflow.log_metric("recall_at_1", 0.94)
    mlflow.log_metric("latency_p95", 1.2)
```

UI: http://localhost:5000

## RAGAS Evaluation

```python
from src.evaluation.ragas_evaluation import evaluate_with_ragas

scores = await evaluate_with_ragas(
    questions=questions,
    answers=answers,
    contexts=contexts,
    ground_truths=ground_truths,
)
# {"faithfulness": 0.92, "answer_relevancy": 0.88, ...}
```

## LightRAG (Experimental)

Graph-based retrieval for complex queries:

```python
# Container: dev-lightrag (9621)
# Uses OpenAI for graph construction
# Experimental, not in main pipeline
```

## Dependencies

- Container: `dev-mlflow` (5000)
- Container: `dev-lightrag` (9621) - experimental
- Langfuse for trace comparison

## Trace Validation (#110)

Runtime validation pipeline: rebuild → run queries → collect Langfuse traces → report.

| File | Purpose |
|------|---------|
| `scripts/validate_queries.py` | 30+ queries/collection (gdrive_bge, legal, edge cases) |
| `scripts/validate_traces.py` | Runner: cold/cache phases, Langfuse enrichment, p50/p95 report |
| `docs/reports/` | Generated reports (gitignored) |

```bash
make validate-traces       # Full rebuild + validation
make validate-traces-fast  # No rebuild, just run
uv run python scripts/validate_traces.py --collection gdrive_documents_bge --report
```

**Baseline (2026-02-10):** cold p50=2480ms, p95=5585ms. generate node = 97% of latency.

## LLM-as-a-Judge (#230)

Automated quality scoring via RAG Triad: faithfulness, answer relevance, context relevance.

**Judge model:** GLM-4.7 via LiteLLM (Cerebras free tier), `temperature=0`, JSON mode.

| Metric | Score Name | Threshold | What it measures |
|--------|-----------|-----------|------------------|
| Faithfulness | `judge_faithfulness` | ≥0.75 | Answer grounded in context, no hallucinations |
| Answer Relevance | `judge_answer_relevance` | ≥0.70 | Answer useful and relevant to question |
| Context Relevance | `judge_context_relevance` | ≥0.65 | Retrieved docs relevant to question |

### Modes

| Mode | Command | Description |
|------|---------|-------------|
| Batch | `make eval-judge` | 24h traces, all without judge scores |
| Sample | `make eval-judge-sample` | 48h traces, 50% sample |
| Online | `JUDGE_SAMPLE_RATE=0.2` | Fire-and-forget on live queries |

### Data flow

```
Langfuse traces → fetch (API) → extract query/answer/context
  → 3 judge LLM calls (parallel) → write scores back to Langfuse
```

Context extracted from `node-retrieve` span output field `retrieved_context` (curated: top-5 docs, 500 chars each).

### Online sampling config

| Env Var | Default | Description |
|---------|---------|-------------|
| `JUDGE_SAMPLE_RATE` | `0.0` | Fraction of queries (0.0=off, 0.2=20%) |
| `JUDGE_MODEL` | `gpt-4o-mini-cerebras-glm` | Judge LLM model |

Online judge is semaphore-bounded (max 2 concurrent) with 25s timeout. Errors logged, never affect user response.

## Testing

```bash
pytest tests/unit/test_evaluator.py -v
pytest tests/unit/evaluation/test_judges.py -v     # Judge parser + LLM mock
pytest tests/unit/evaluation/test_runner.py -v      # Trace extraction
pytest tests/unit/evaluation/test_online_sampling.py -v
pytest tests/baseline/ -v
make baseline-smoke
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| MLflow connection | `docker compose up -d mlflow` |
| Missing ground truth | Generate with `create_golden_set.py` |
| RAGAS timeout | Reduce batch size |

## Development Guide

### Adding new metric

1. Add calculation method to `SearchEvaluator`
2. Include in `evaluate_query()` return dict
3. Add to MLflow logging
4. Update baseline thresholds if needed

### Creating golden set

```bash
python src/evaluation/create_golden_set.py \
    --input queries.txt \
    --output ground_truth.json
```
