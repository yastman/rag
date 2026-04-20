***REMOVED*** 📊 Evaluation & Observability

This folder contains all evaluation, experimentation, and observability tools for the RAG system.

***REMOVED******REMOVED*** 📁 Contents

| Category | Files | Purpose |
|----------|-------|---------|
| **Observability** | `mlflow_integration.py`, `langfuse_integration.py` | Production monitoring and tracing |
| **Quality Evaluation** | `ragas_evaluation.py`, `evaluate_with_ragas.py`, `evaluator.py` | Quality metrics (RAGAS framework) |
| **Testing** | `create_golden_set.py`, `generate_test_queries.py`, `smoke_test.py` | Test data generation and smoke tests |
| **Experimentation** | `mlflow_experiments.py`, `run_ab_test.py`, `test_mlflow_ab.py` | A/B testing and experiments |
| **Search Engines** | `search_engines.py`, `search_engines_rerank.py` | Search implementations for evaluation |
| **Legacy** | `config_snapshot.py`, `metrics_logger.py` | Replaced by MLflow/Langfuse |

---

***REMOVED******REMOVED*** 🔭 Observability Stack

***REMOVED******REMOVED******REMOVED*** MLflow Integration (`mlflow_integration.py`)

**Purpose**: Development and experimentation tracking.

**Key Features**:
- Experiment versioning and comparison
- Config snapshots (search engine, embeddings, chunking)
- Metrics logging (precision, recall, latency, cost)
- Artifact storage (reports, configs, query results)
- Model Registry integration

**Usage**:
```python
from evaluation.mlflow_integration import MLflowRAGLogger

logger = MLflowRAGLogger(experiment_name="contextual_rag")

with logger.start_run(run_name="dbsf_colbert_v2.0.1"):
    ***REMOVED*** Log config
    logger.log_config({
        "search_engine": "DBSF + ColBERT",
        "embedding_model": "bge-m3",
        "chunk_size": 512,
        "top_k": 10,
    })

    ***REMOVED*** Log metrics
    logger.log_metrics({
        "precision@1": 0.94,
        "recall@10": 0.98,
        "latency_p95_ms": 420,
        "cost_per_1000": 0.12,
    })

    ***REMOVED*** Log artifacts
    logger.log_artifact("reports/AB_TEST_REPORT.md")

    ***REMOVED*** Get config hash for versioning
    config_hash = logger.get_config_hash()
```

**MLflow UI**: http://localhost:5000

---

***REMOVED******REMOVED******REMOVED*** Langfuse Integration (`langfuse_integration.py`)

**Purpose**: Production observability and LLM tracing.

**Key Features**:
- Real-time query tracing with `@observe()` decorator
- Nested spans (retrieval → reranking → generation)
- Session and user tracking
- Cost monitoring per query
- Production error handling

**Usage**:
```python
from langfuse import observe, get_client, propagate_attributes

@observe(name="rag-query")
def search_query(query: str, user_id: str):
    langfuse = get_client()

    with propagate_attributes(
        session_id="session_abc",
        user_id=user_id,
        tags=["production", "criminal-code"],
    ):
        langfuse.update_current_span(input={"query": query})

        ***REMOVED*** Your search logic
        results = engine.search(query, top_k=10)

        ***REMOVED*** Log metrics
        langfuse.score_current_trace(
            name="precision_at_1",
            value=calculate_precision(results)
        )

        langfuse.update_current_span(output={"num_results": len(results)})

    return results
```

**Langfuse UI**: http://localhost:3001

---

***REMOVED******REMOVED******REMOVED*** When to Use MLflow vs Langfuse?

| Use Case | Tool | Why |
|----------|------|-----|
| **Development** (A/B tests, experiments) | MLflow | Batch processing, experiment comparison |
| **Production** (live queries) | Langfuse | Real-time tracing, cost per query |
| **Quality baselines** (RAGAS nightly runs) | MLflow | Aggregated metrics, trend analysis |
| **Debugging** (why did this query fail?) | Langfuse | Detailed spans, individual query traces |
| **Model governance** (promote to prod) | MLflow | Model Registry, staging workflow |

---

***REMOVED******REMOVED*** ✅ Quality Evaluation (RAGAS)

***REMOVED******REMOVED******REMOVED*** Golden Test Set (`create_golden_set.py`)

**Purpose**: Generate 150 queries with ground truth for RAGAS evaluation.

**Test Set Categories**:
1. **Article lookup** (50 queries, easy): `"Стаття 121 УК України"`
2. **Crime definitions** (40 queries, medium): `"Що таке шахрайство?"`
3. **Legal concepts** (30 queries, medium): `"Які злочини проти власності?"`
4. **Procedures** (20 queries, hard): `"Як подати апеляцію?"`
5. **Legal definitions** (10 queries, hard): `"Що таке презумпція невинуватості?"`

**Usage**:
```bash
***REMOVED*** Generate golden test set
cd /srv/contextual_rag
python -m src.evaluation.create_golden_set

***REMOVED*** Output: tests/data/golden_test_set.json (150 queries)
```

**Output Format**:
```json
{
  "metadata": {
    "total_queries": 150,
    "categories": {"lookup": 50, "definitions": 40, ...},
    "created_at": "2025-10-30T14:30:00Z"
  },
  "queries": [
    {
      "id": 1,
      "query": "Стаття 115 УК України",
      "expected_articles": [115],
      "category": "lookup",
      "difficulty": "easy"
    }
  ]
}
```

---

***REMOVED******REMOVED******REMOVED*** RAGAS Evaluator (`ragas_evaluation.py`)

**Purpose**: Run RAGAS quality evaluation and log to MLflow.

**RAGAS Metrics**:
- **Faithfulness** ≥ 0.85: Claims in answer are grounded in context
- **Context Precision** ≥ 0.80: Retrieved chunks are relevant
- **Context Recall** ≥ 0.90: Ground truth is in retrieved context
- **Answer Relevancy**: Answer addresses the query

**Usage**:
```python
from evaluation.ragas_evaluation import RAGASEvaluator

evaluator = RAGASEvaluator()

***REMOVED*** Run evaluation on golden test set
results = await evaluator.evaluate_pipeline(
    rag_pipeline=my_rag,
    golden_test_set_path="tests/data/golden_test_set.json"
)

***REMOVED*** Check if acceptance criteria passed
if results["acceptance_passed"]:
    print("✅ Quality baseline met!")
else:
    print(f"❌ Failed: {results['metrics']}")
```

**Automated Nightly Run**:
```bash
***REMOVED*** Add to crontab for nightly evaluation
crontab -e

***REMOVED*** Run RAGAS evaluation at 2 AM daily
0 2 * * * cd /srv/contextual_rag && /srv/app/venv/bin/python -m src.evaluation.ragas_evaluation >> /srv/logs/ragas_nightly.log 2>&1
```

---

***REMOVED******REMOVED******REMOVED*** Full RAGAS Evaluation (`evaluate_with_ragas.py`)

**Purpose**: Comprehensive RAGAS evaluation with detailed reporting.

**Features**:
- Supports all RAGAS metrics (faithfulness, precision, recall, relevancy)
- Generates detailed reports
- Integrates with MLflow for tracking
- Category-wise breakdown

**Usage**:
```bash
***REMOVED*** Run full evaluation
python -m src.evaluation.evaluate_with_ragas \
  --test-set tests/data/golden_test_set.json \
  --output reports/ragas_report.json
```

---

***REMOVED******REMOVED******REMOVED*** General Evaluator (`evaluator.py`)

**Purpose**: Unified evaluation interface for multiple metrics.

**Supported Metrics**:
- Precision@K
- Recall@K
- F1@K
- MRR (Mean Reciprocal Rank)
- NDCG (Normalized Discounted Cumulative Gain)
- Latency (P50, P95, P99)

**Usage**:
```python
from evaluation.evaluator import RAGEvaluator

evaluator = RAGEvaluator()

results = evaluator.evaluate(
    queries=test_queries,
    ground_truth=expected_results,
    metrics=["precision@1", "recall@10", "latency_p95"]
)
```

---

***REMOVED******REMOVED*** 🧪 A/B Testing & Experiments

***REMOVED******REMOVED******REMOVED*** Experiment Manager (`mlflow_experiments.py`)

**Purpose**: A/B testing framework with MLflow tracking.

**Features**:
- Champion vs Challenger comparison
- Statistical significance testing (t-test, Mann-Whitney U)
- Automated metric logging
- Rollback support

**Usage**:
```python
from evaluation.mlflow_experiments import ABTestRunner

runner = ABTestRunner(experiment_name="search_engine_comparison")

***REMOVED*** Run A/B test
results = runner.run_ab_test(
    champion_config={"engine": "DBSF", "top_k": 10},
    challenger_config={"engine": "DBSF + ColBERT", "top_k": 10},
    test_queries=golden_test_set,
    metrics=["precision@1", "recall@10", "latency_p95"]
)

***REMOVED*** Check if challenger wins
if results["challenger_wins"]:
    print(f"🏆 Challenger wins! Improvement: {results['improvement']:.2%}")
    runner.promote_challenger()
else:
    print("Champion remains superior")
```

---

***REMOVED******REMOVED******REMOVED*** A/B Test Runner (`run_ab_test.py`)

**Purpose**: CLI tool for running A/B tests.

**Usage**:
```bash
***REMOVED*** Run A/B test from command line
python -m src.evaluation.run_ab_test \
  --champion-config configs/champion.json \
  --challenger-config configs/challenger.json \
  --test-set tests/data/golden_test_set.json \
  --output reports/AB_TEST_REPORT.md

***REMOVED*** Example output:
***REMOVED*** 🏆 A/B Test Results
***REMOVED*** Champion: DBSF (baseline)
***REMOVED*** Challenger: DBSF + ColBERT (v2.0.1)
***REMOVED***
***REMOVED*** Metrics:
***REMOVED***   Precision@1: 0.89 → 0.94 (+5.6% ✅)
***REMOVED***   Recall@10: 0.95 → 0.98 (+3.2% ✅)
***REMOVED***   Latency P95: 380ms → 420ms (+10.5% ⚠️)
***REMOVED***
***REMOVED*** Statistical Significance: p < 0.001
***REMOVED*** Recommendation: PROMOTE CHALLENGER
```

---

***REMOVED******REMOVED******REMOVED*** Test MLflow A/B (`test_mlflow_ab.py`)

**Purpose**: Unit tests for MLflow A/B testing integration.

**Usage**:
```bash
***REMOVED*** Run tests
pytest src/evaluation/test_mlflow_ab.py -v
```

---

***REMOVED******REMOVED*** 🔍 Search Engine Implementations

***REMOVED******REMOVED******REMOVED*** Search Engines (`search_engines.py`)

**Purpose**: Multiple search engine implementations for evaluation.

**Available Engines**:
1. **DBSF** (Dense-BM25-Sparse-Fusion): Baseline
2. **ColBERT**: Late interaction reranking
3. **Hybrid**: Dense + Sparse combination
4. **Semantic Only**: Pure vector search
5. **BM25 Only**: Pure keyword search

**Usage**:
```python
from evaluation.search_engines import DBSFSearchEngine, ColBERTSearchEngine

***REMOVED*** Initialize engine
engine = DBSFSearchEngine(
    qdrant_url="http://localhost:6333",
    collection_name="contextual_rag_criminal_code_v1"
)

***REMOVED*** Search
results = engine.search(
    query="Стаття 121 УК України",
    top_k=10
)
```

---

***REMOVED******REMOVED******REMOVED*** Search Engines Rerank (`search_engines_rerank.py`)

**Purpose**: Reranking strategies for search engines.

**Reranking Methods**:
- Cross-encoder reranking
- ColBERT late interaction
- MMR (Maximal Marginal Relevance)
- Diversity-based reranking

---

***REMOVED******REMOVED*** 🧪 Testing

***REMOVED******REMOVED******REMOVED*** Smoke Test (`smoke_test.py`)

**Purpose**: Quick health check for RAG system.

**Tests**:
- Qdrant connection
- Collection health (point count, index status)
- Search functionality (5 sample queries)
- Latency check (< 1 second)
- BGE-M3 embeddings service

**Usage**:
```bash
***REMOVED*** Run smoke test
python -m src.evaluation.smoke_test

***REMOVED*** Output:
***REMOVED*** ✅ Qdrant connection: OK
***REMOVED*** ✅ Collection health: 45,234 points
***REMOVED*** ✅ Sample queries: 5/5 passed
***REMOVED*** ✅ Latency P95: 380ms
***REMOVED*** ✅ BGE-M3 service: OK
***REMOVED***
***REMOVED*** 🎉 All smoke tests passed!
```

**Automated Run** (after deployments):
```bash
***REMOVED*** In CI/CD pipeline
./deploy.sh && python -m src.evaluation.smoke_test || rollback
```

---

***REMOVED******REMOVED*** 📚 Supporting Files

***REMOVED******REMOVED******REMOVED*** Generate Test Queries (`generate_test_queries.py`)

**Purpose**: Generate synthetic test queries for specific legal topics.

**Usage**:
```python
from evaluation.generate_test_queries import QueryGenerator

generator = QueryGenerator()

queries = generator.generate(
    topics=["шахрайство", "крадіжка", "розбій"],
    num_per_topic=10
)
```

---

***REMOVED******REMOVED******REMOVED*** Extract Ground Truth (`extract_ground_truth.py`)

**Purpose**: Extract ground truth from expert annotations.

**Usage**:
```bash
***REMOVED*** Extract ground truth from CSV
python -m src.evaluation.extract_ground_truth \
  --input data/expert_annotations.csv \
  --output tests/data/ground_truth.json
```

---

***REMOVED******REMOVED*** 🗂️ Legacy Files (Deprecated)

***REMOVED******REMOVED******REMOVED*** ❌ Config Snapshot (`config_snapshot.py`)

**Status**: Replaced by `mlflow_integration.py`

**Why deprecated**: MLflow provides better versioning, comparison, and Model Registry integration.

---

***REMOVED******REMOVED******REMOVED*** ❌ Metrics Logger (`metrics_logger.py`)

**Status**: Replaced by `langfuse_integration.py`

**Why deprecated**: Langfuse provides real-time tracing and cost monitoring.

---

***REMOVED******REMOVED*** 📊 Evaluation Workflow

***REMOVED******REMOVED******REMOVED*** Development (Pre-production)

```bash
***REMOVED*** 1. Create golden test set (once)
python -m src.evaluation.create_golden_set

***REMOVED*** 2. Run A/B test
python -m src.evaluation.run_ab_test \
  --champion-config configs/baseline.json \
  --challenger-config configs/new_version.json \
  --test-set tests/data/golden_test_set.json

***REMOVED*** 3. If challenger wins, run RAGAS validation
python -m src.evaluation.ragas_evaluation

***REMOVED*** 4. Check MLflow UI for results
open http://localhost:5000
```

---

***REMOVED******REMOVED******REMOVED*** Production (Monitoring)

```bash
***REMOVED*** 1. Run smoke test after deployment
python -m src.evaluation.smoke_test

***REMOVED*** 2. Enable Langfuse tracing in production
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."

***REMOVED*** 3. Monitor Langfuse dashboard
open http://localhost:3001

***REMOVED*** 4. RAGAS runs nightly via cron (see crontab)
crontab -l | grep ragas
```

---

***REMOVED******REMOVED*** 🎯 Acceptance Criteria

All experiments must meet these criteria before production:

| Metric | Threshold | Measured By |
|--------|-----------|-------------|
| **Faithfulness** | ≥ 0.85 | RAGAS (nightly) |
| **Context Precision** | ≥ 0.80 | RAGAS (nightly) |
| **Context Recall** | ≥ 0.90 | RAGAS (nightly) |
| **Precision@1** | ≥ 0.90 | A/B tests |
| **Latency P95** | ≤ 500ms | Smoke tests |
| **Cost per 1000** | ≤ $3 | Langfuse (production) |

---

***REMOVED******REMOVED*** 🔧 Configuration

***REMOVED******REMOVED******REMOVED*** Environment Variables

```bash
***REMOVED*** MLflow
export MLFLOW_TRACKING_URI="http://localhost:5000"

***REMOVED*** Langfuse
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."
export LANGFUSE_HOST="http://localhost:3001"

***REMOVED*** Qdrant
export QDRANT_URL="http://localhost:6333"
export QDRANT_COLLECTION="contextual_rag_criminal_code_v1"

***REMOVED*** RAGAS (optional - uses GPT-4 for evaluation)
export OPENAI_API_KEY=[REDACTED-OPENAI-KEY]
```

---

***REMOVED******REMOVED*** 📈 Metrics Reference

***REMOVED******REMOVED******REMOVED*** RAGAS Metrics

- **Faithfulness**: Measures if answer claims are supported by context
  - Formula: `faithful_claims / total_claims`
  - Good: ≥ 0.85

- **Context Precision**: Measures if retrieved chunks are relevant
  - Formula: Based on ground truth relevance ranking
  - Good: ≥ 0.80

- **Context Recall**: Measures if ground truth is in retrieved context
  - Formula: `ground_truth_in_context / total_ground_truth`
  - Good: ≥ 0.90

- **Answer Relevancy**: Measures if answer addresses the query
  - Formula: Cosine similarity between query and answer embeddings
  - Good: ≥ 0.85

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team
