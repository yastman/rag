# 🚀 Migration Plan: Custom Scripts → Production Tools

**Goal:** Replace custom scripts (923 lines) with production-grade tools in 2-3 days.

**Status:** ✅ **COMPLETED** (2025-10-23)

---

## 📋 Completion Status

| Phase | Status | Completion Date | Documentation |
|------|--------|-----------------|--------------|
| **Phase 1:** MLflow + RAGAS Infrastructure | ✅ Completed | 2025-10-23 | [PHASE1_COMPLETION_SUMMARY.md](PHASE1_COMPLETION_SUMMARY.md) |
| **Phase 2:** MLflow Integration in run_ab_test.py | ✅ Completed | 2025-10-23 | [PHASE2_COMPLETION_SUMMARY.md](PHASE2_COMPLETION_SUMMARY.md) |
| **Phase 3:** Langfuse Native SDK Integration | ✅ Completed | 2025-10-23 | [PHASE3_COMPLETION_SUMMARY.md](PHASE3_COMPLETION_SUMMARY.md) |

**Total:** All 3 phases completed, production-ready ML platform deployed.

---

## 📊 What We're Replacing

| Component | Before (our code) | After | Benefit |
|-----------|---------------|---------|---------|
| Config versioning | config_snapshot.py (67 lines) | **MLflow** | UI + reproducibility |
| E2E evaluation | ❌ None | **RAGAS** | 4 metrics out-of-the-box |
| Metrics logging | metrics_logger.py (403 lines) | **Langfuse** | Full observability |
| Smoke testing | smoke_test.py (453 lines) | **Giskard** | Auto-tests + reports |

---

## 🎯 Phased Migration

### ✅ Phase 1 (Day 1): MLflow + RAGAS - Quick Wins

**Goal:** Experiment reproducibility + e2e metrics
**Time:** 4 hours
**Risk:** 🟢 Minimal

#### Step 1.1: Create virtual environment (15 min)

```bash
cd /srv/contextual_rag
python3 -m venv venv
source venv/bin/activate

# Save current dependencies
pip freeze > requirements_current.txt
```

#### Step 1.2: Install MLflow (15 min)

```bash
pip install mlflow==2.22.1
pip install boto3  # If using S3 for artifacts

# Start MLflow UI
mlflow ui --backend-store-uri ./mlruns --port 5001
# Open: http://localhost:5001
```

#### Step 1.3: Integrate MLflow in run_ab_test.py (1.5 hours)

Create `evaluation/mlflow_integration.py`:

```python
"""MLflow integration wrapper for A/B tests."""
import mlflow
from config_snapshot import get_config_hash, CONFIG_SNAPSHOT

def log_ab_test(engine_name: str, results: dict, report_path: str):
    """Log A/B test results to MLflow."""

    with mlflow.start_run(run_name=f"{engine_name}_evaluation"):
        # Log parameters
        mlflow.log_param("engine", engine_name)
        mlflow.log_param("config_hash", get_config_hash())
        mlflow.log_param("collection", results["collection"])
        mlflow.log_param("queries_count", results["queries_count"])

        # Log search config as nested params
        engine_config = CONFIG_SNAPSHOT["search_engines"].get(engine_name, {})
        for key, value in engine_config.items():
            mlflow.log_param(f"search.{key}", value)

        # Log metrics
        mlflow.log_metric("recall_at_1", results["recall_at_1"])
        mlflow.log_metric("recall_at_10", results["recall_at_10"])
        mlflow.log_metric("ndcg_at_10", results["ndcg_at_10"])
        mlflow.log_metric("mrr", results["mrr"])
        mlflow.log_metric("latency_p50_ms", results["latency_p50_ms"])
        mlflow.log_metric("latency_p95_ms", results["latency_p95_ms"])

        # Log artifacts
        mlflow.log_artifact(report_path, artifact_path="reports")

        # Log tags
        mlflow.set_tag("experiment_type", "ab_test")
        mlflow.set_tag("qdrant_version", CONFIG_SNAPSHOT["infrastructure"]["qdrant_version"])
        mlflow.set_tag("embedder", CONFIG_SNAPSHOT["models"]["embedder"]["name"])
```

Add to `evaluation/run_ab_test.py`:

```python
from mlflow_integration import log_ab_test

# At the end of run_evaluation() function:
if args.mlflow:
    log_ab_test(engine_name, results, report_path)
```

#### Step 1.4: Install RAGAS (30 min)

```bash
pip install ragas==0.1.20 langchain-openai==0.3.2

# Add to .env
echo "OPENAI_API_KEY=your_key_here" >> .env
```

#### Step 1.5: Create evaluate_with_ragas.py (1.5 hours)

```python
#!/usr/bin/env python3
"""
RAGAS E2E Evaluation for RAG System

Evaluates faithfulness, context relevance, answer relevancy for all queries.
"""
import json
import mlflow
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    Faithfulness,
    ContextRelevance,
    AnswerRelevancy,
    ContextRecall,
)
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI

from search_engines import HybridDBSFColBERTSearchEngine
from config_snapshot import get_config_hash

def create_ragas_dataset(engine, queries_file: str, limit: int = 50):
    """Create RAGAS dataset from search results."""
    with open(queries_file) as f:
        queries = json.load(f)[:limit]

    dataset_dict = {
        "question": [],
        "contexts": [],
        "answer": [],
        "ground_truth": []
    }

    for query_data in queries:
        query = query_data["query"]
        expected_article = query_data.get("expected_article")

        # Search
        results = engine.search(query, limit=5)

        # Extract contexts
        contexts = [r.payload.get("text", "") for r in results]

        # Generate answer (top result)
        answer = results[0].payload.get("text", "") if results else ""

        # Ground truth (expected article text)
        ground_truth = query_data.get("ground_truth", "")

        dataset_dict["question"].append(query)
        dataset_dict["contexts"].append(contexts)
        dataset_dict["answer"].append(answer)
        dataset_dict["ground_truth"].append(ground_truth)

    return Dataset.from_dict(dataset_dict)

def run_ragas_evaluation(engine_name: str = "dbsf_colbert"):
    """Run RAGAS evaluation and log to MLflow."""

    # Initialize engine
    engine = HybridDBSFColBERTSearchEngine(collection_name="uk_civil_code_v2")

    # Create dataset
    print("📊 Creating RAGAS dataset...")
    dataset = create_ragas_dataset(
        engine,
        queries_file="data/queries_testset.json",
        limit=50  # Start with 50 queries
    )

    # Initialize LLM for evaluation
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    evaluator_llm = LangchainLLMWrapper(llm)

    # Define metrics
    metrics = [
        Faithfulness(llm=evaluator_llm),
        ContextRelevance(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
    ]

    # Run evaluation
    print("🔍 Running RAGAS evaluation...")
    with mlflow.start_run(run_name=f"ragas_{engine_name}"):
        # Log params
        mlflow.log_param("engine", engine_name)
        mlflow.log_param("config_hash", get_config_hash())
        mlflow.log_param("evaluator_llm", "gpt-4o-mini")
        mlflow.log_param("evaluator_temperature", 0.0)
        mlflow.log_param("ragas_version", "0.1.20")
        mlflow.log_param("queries_count", len(dataset))

        # Evaluate
        results = evaluate(dataset=dataset, metrics=metrics)

        # Log metrics
        for metric_name, value in results.items():
            mlflow.log_metric(f"ragas_{metric_name}", value)

        # Log results as artifact
        results_df = results.to_pandas()
        results_df.to_csv("/tmp/ragas_results.csv", index=False)
        mlflow.log_artifact("/tmp/ragas_results.csv", artifact_path="ragas")

        print("\n✅ RAGAS Evaluation Complete!")
        print(results)

if __name__ == "__main__":
    run_ragas_evaluation()
```

#### Step 1.6: Testing (30 min)

```bash
# Start MLflow UI
mlflow ui --backend-store-uri ./mlruns --port 5001 &

# Run A/B test with MLflow
source venv/bin/activate
cd evaluation
python run_ab_test.py --engines dbsf_colbert --mlflow

# Run RAGAS evaluation
python evaluate_with_ragas.py

# Check UI: http://localhost:5001
```

**✅ Phase 1 Results:**
- All experiments in MLflow UI
- 4 new metrics from RAGAS
- Compare different runs
- Full reproducibility

---

### ✅ Phase 2 (Day 2): MLflow Integration in run_ab_test.py - COMPLETED

**Goal:** Automatic A/B test logging in MLflow
**Time:** 2 hours (planned: 6 hours)
**Risk:** 🟢 Minimal
**Status:** ✅ **COMPLETED** (2025-10-23)

**Implementation:**
- Added optional logging in `run_ab_test.py` (+85 lines)
- Graceful degradation: works with/without MLflow
- Logs: 5 parameters + 25 metrics + markdown report
- Created test script `test_mlflow_ab.py` for quick checks

Details: [PHASE2_COMPLETION_SUMMARY.md](PHASE2_COMPLETION_SUMMARY.md)

---

### ✅ Phase 3 (Day 2-3): Langfuse - Production Observability - COMPLETED

**Goal:** Production request tracing with native SDK
**Time:** 3 hours (planned: 6 hours)
**Risk:** 🟢 Minimal (used native SDK)
**Status:** ✅ **COMPLETED** (2025-10-23)

#### Step 2.1: Install Langfuse (1 hour)

**Option A: Self-hosted (recommended)**

Add to `/srv/docker-compose.yml`:

```yaml
  langfuse-server:
    image: langfuse/langfuse:2
    container_name: ai-langfuse
    depends_on:
      - ai-postgres
    ports:
      - "3001:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@ai-postgres:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_SECRET}
      - SALT=${LANGFUSE_SALT}
      - NEXTAUTH_URL=http://localhost:3001
    networks:
      - ai-unified-network
```

Create DB:

```bash
docker exec -it ai-postgres psql -U postgres -c "CREATE DATABASE langfuse;"

# Add to .env
echo "LANGFUSE_SECRET=$(openssl rand -hex 32)" >> .env
echo "LANGFUSE_SALT=$(openssl rand -hex 32)" >> .env

# Restart
docker compose up -d langfuse-server
```

**Option B: Cloud (faster)**

```bash
# Get keys from https://cloud.langfuse.com
echo "LANGFUSE_PUBLIC_KEY=pk-lf-..." >> .env
echo "LANGFUSE_SECRET_KEY=sk-lf-..." >> .env
echo "LANGFUSE_HOST=https://cloud.langfuse.com" >> .env
```

#### Step 2.2: Install Python SDK (15 min)

```bash
pip install langfuse==2.56.0
```

#### Step 2.3: Create langfuse_integration.py with native SDK (1 hour) ✅

**Actual implementation:** Used official Langfuse SDK without custom wrappers

Created `evaluation/langfuse_integration.py` (430 lines):

```python
"""
Langfuse Integration for Production RAG Observability - Native SDK Usage

Uses official Langfuse Python SDK patterns with @observe() decorator.
No custom wrappers - just native SDK features.
"""
from langfuse import Langfuse, observe, get_client

# Helper function with native decorator
@observe(name="rag-search-query")
def trace_search_with_decorator(
    query: str,
    search_fn: callable,
    engine_name: str = "unknown",
    user_id: str = "anonymous",
    session_id: str | None = None,
    expected_article: int | None = None,
) -> tuple[list[Any], dict[str, float]]:
    """Trace a RAG search query using native @observe() decorator."""
    langfuse = get_client()

    # Update trace with metadata
    langfuse.update_current_trace(
        input={"query": query, "engine": engine_name},
        user_id=user_id,
        session_id=session_id,
        tags=["search", engine_name, "evaluation"]
    )

    # Execute search
    results = search_fn(query)

    # Log scores
    if expected_article:
        precision = calculate_precision(results, expected_article)
        langfuse.score_current_trace(name="precision_at_1", value=precision)

    return results

# Manual spans for fine-grained control
def trace_search_with_spans(query, search_fn, engine_name):
    """Trace using manual span creation for complex pipelines."""
    langfuse = get_client()

    with langfuse.start_as_current_span(name="rag-search") as trace:
        # Retrieval span
        with trace.start_as_current_span(name="retrieval") as span:
            results = search_fn(query)
            span.update(output={"num_results": len(results)})

        # Evaluation span
        with trace.start_as_current_span(name="evaluation") as span:
            metrics = calculate_metrics(results)
            span.score(name="precision_at_1", value=metrics["p@1"])
```

**Native SDK benefits:**
- No custom wrappers → less code, fewer bugs
- Automatic nesting of decorated functions
- Official patterns from documentation
- Out-of-the-box support from Langfuse team

#### Step 2.4: Add custom scores (1 hour)

```python
from langfuse import Langfuse

langfuse = Langfuse()

def log_search_metrics(trace_id: str, precision_at_1: float, latency_ms: float):
    """Log custom metrics to Langfuse."""
    langfuse.score(
        trace_id=trace_id,
        name="precision_at_1",
        value=precision_at_1
    )
    langfuse.score(
        trace_id=trace_id,
        name="latency_ms",
        value=latency_ms
    )
```

#### Step 2.5: Testing (30 min)

```bash
# Open Langfuse UI
open http://localhost:3001  # Self-hosted
# or
open https://cloud.langfuse.com  # Cloud

# Run test with tracing
python run_ab_test.py --engines dbsf_colbert --sample 10

# Check traces in UI
```

**✅ Phase 2 Results:**
- Full tracing: encode → search → rerank
- Latency breakdown by steps
- Custom scores (P@1, latency)
- Production-ready observability

---

### ✅ Phase 3 (Optional): Giskard - Automated Testing

**Goal:** Automated quality checks + HTML reports
**Time:** 4 hours
**Risk:** 🟢 Minimal

#### Step 3.1: Install Giskard (15 min)

```bash
pip install giskard==2.15.4
```

#### Step 3.2: Create giskard_smoke_tests.py (3 hours)

```python
#!/usr/bin/env python3
"""Giskard automated smoke tests for RAG."""
import giskard as gsk
from search_engines import HybridDBSFColBERTSearchEngine

# Wrap search engine
def rag_model(query: str) -> str:
    """RAG model wrapper for Giskard."""
    engine = HybridDBSFColBERTSearchEngine(collection_name="uk_civil_code_v2")
    results = engine.search(query, limit=1)
    return results[0].payload.get("text", "") if results else ""

# Create Giskard model
model = gsk.Model(
    rag_model,
    model_type="text_generation",
    name="DBSF+ColBERT RAG",
    description="Ukrainian Criminal Code RAG system"
)

# Load smoke queries
with open("data/smoke_queries.json") as f:
    smoke_queries = json.load(f)

dataset = gsk.Dataset(
    pd.DataFrame({"query": [q["query"] for q in smoke_queries]}),
    target=None
)

# Create test suite
suite = gsk.Suite()

# Add tests
suite.add_test(
    gsk.testing.test_llm_output_against_rules(
        model=model,
        dataset=dataset,
        rules=["Output must contain article number", "Output must be in Ukrainian"]
    )
)

suite.add_test(
    gsk.testing.test_llm_similarity(
        model=model,
        dataset=dataset,
        threshold=0.8
    )
)

# Run and generate report
results = suite.run()
results.to_html("evaluation/reports/giskard_smoke_report.html")
```

#### Step 3.3: CI/CD Integration (30 min)

Create `.github/workflows/smoke_test.yml`:

```yaml
name: Smoke Test with Giskard

on: [push, pull_request]

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run Giskard smoke tests
        run: |
          python evaluation/giskard_smoke_tests.py
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: smoke-test-report
          path: evaluation/reports/giskard_smoke_report.html
```

**✅ Phase 3 Results:**
- Automated smoke tests
- HTML reports
- CI/CD integration
- Checks for hallucinations, bias, prompt injection

---

## ⚠️ Risks and Mitigation

### Risk 1: LLM versioning for RAGAS

**Problem:** RAGAS scores may change when LLM version changes
**Mitigation:**
- Fix `gpt-4o-mini` + `temperature=0.0` in MLflow params
- Run evaluation multiple times and check variance
- Use `ragas_version` as tag

### Risk 2: Secrets in repository

**Problem:** OpenAI keys, Langfuse keys may get into git
**Mitigation:**
- All keys only in `.env` (already in `.gitignore`)
- Use environment variables in CI/CD
- Add pre-commit hook for secret checking

### Risk 3: Latency overhead from tracing

**Problem:** Langfuse may add latency
**Mitigation:**
- Async sending to Langfuse (by default)
- Measure overhead: run A/B with/without tracing
- Configure sampling (don't log every request in prod)

### Risk 4: PII in traces

**Problem:** User queries may contain personal data
**Mitigation:**
- For test data (150 queries) - not a problem
- For production: enable PII masking in Langfuse
- Regularly clean old traces

---

## 📦 Final Architecture

```
contextual_rag/
├── venv/                          # 🆕 Virtual environment
├── mlruns/                        # 🆕 MLflow experiments
├── evaluation/
│   ├── search_engines.py          # ✅ No changes
│   ├── run_ab_test.py             # 🔄 + MLflow logging
│   ├── mlflow_integration.py      # 🆕 MLflow wrapper
│   ├── evaluate_with_ragas.py     # 🆕 RAGAS evaluation
│   ├── langfuse_integration.py    # 🆕 Langfuse tracing
│   ├── giskard_smoke_tests.py     # 🆕 Giskard tests
│   ├── config_snapshot.py         # 📦 Deprecated → MLflow
│   ├── smoke_test.py              # 📦 Deprecated → Giskard
│   └── metrics_logger.py          # 📦 Deprecated → Langfuse
├── docker-compose.yml             # 🔄 + Langfuse service
├── .env                           # 🔄 + API keys
└── requirements.txt               # 🔄 Updated

🆕 New tools:
- MLflow UI: http://localhost:5001
- Langfuse UI: http://localhost:3001
```

---

## 📊 Expected Results

| Metric | Before migration | After migration |
|---------|------------|----------------|
| **Lines of custom code** | 923 | ~150 (-84%) |
| **UI dashboards** | 0 | 2 (MLflow + Langfuse) |
| **RAG metrics** | 5 (R@1, R@10, NDCG, MRR, latency) | 9 (+4 RAGAS) |
| **Tracing** | ❌ None | ✅ Full pipeline |
| **Auto-tests** | Manual | ✅ Automated |
| **Reproducibility** | Hash only | ✅ Full experiment tracking |
| **Production-ready** | 🟡 Partial | ✅ Yes |

---

## 🚀 Next Steps

1. **Read and approve the plan**
2. **Start with Phase 1** (MLflow + RAGAS) → 4 hours work
3. **Check results** in MLflow UI
4. **Move to Phase 2** (Langfuse) → production observability
5. **Optional Phase 3** (Giskard) → automated testing

**Ready to start?** Say "go Phase 1" and I'll immediately create all necessary files and start installation.
