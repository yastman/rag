# 🎯 MLflow + Langfuse Integration Plan 2025

> **Comprehensive plan for integrating ML observability and experimentation into Contextual RAG Pipeline**

**Author**: Claude Code
**Date**: 2025-10-30
**Status**: Planning Phase
**Project**: Contextual RAG v2.0.1

---

## 📋 Executive Summary

### What are these services?

**MLflow** = ML Experiment Tracking & Model Management
- Track experiments with different configurations
- Compare results across runs
- Version models and configs
- Batch evaluation and A/B testing
- **Best for**: Development, research, comparing approaches

**Langfuse** = LLM Observability & Production Monitoring
- Real-time tracing of every LLM call
- Cost and latency monitoring
- Debug individual queries
- User session analytics
- **Best for**: Production, debugging, cost optimization

**RAGAS** = RAG Quality Evaluation Framework
- Automated quality metrics (faithfulness, context precision/recall)
- Offline evaluation with golden test sets
- Nightly regression testing
- **Best for**: Quality assurance, baseline measurements

**OpenTelemetry** = Distributed Tracing & System Metrics
- End-to-end request tracing (CPU/RAM/I/O)
- System observability beyond LLM calls
- Integration with Prometheus/Grafana/Tempo
- **Best for**: System performance, bottleneck identification

### Key Principle (2025 Best Practice)

```
Development & Experiments → MLflow + RAGAS
Production & Monitoring   → Langfuse + OpenTelemetry
Cache Layer              → Redis (semantic + response caching)
Data Governance          → Model Registry + Qdrant backups
```

---

## 🏗️ Architecture: Where to Use What

### Current RAG Pipeline Stages

```
┌─────────────────────────────────────────────────────────────────┐
│                   PRODUCTION RAG PIPELINE 2025                  │
└─────────────────────────────────────────────────────────────────┘

1️⃣  INGESTION PIPELINE
    ├── PDF Parsing (PyMuPDF)
    ├── Chunking (PyMuPDFChunker)
    ├── Contextualization (Z.AI LLM)        ← Langfuse: trace LLM
    ├── Embedding (BGE-M3)                  ← Redis: cache embeddings (TTL: 30d)
    └── Indexing (Qdrant)                   ← Backup: nightly snapshots
    📊 MLflow: Track ingestion experiments
    📈 RAGAS: Evaluate chunking quality

2️⃣  RETRIEVAL PIPELINE
    ├── Query Embedding (BGE-M3)            ← Redis: cache by query hash
    ├── Vector Search (Qdrant)              ← OTEL: trace search latency
    ├── Reranking (DBSF/ColBERT)            ← OTEL: trace rerank time
    └── Result Fusion                       ← Redis: cache results (TTL: 5-60min)
    📊 MLflow: Track search configs
    📈 Langfuse: Monitor query performance
    🔬 RAGAS: Nightly quality checks (faithfulness, precision, recall)

3️⃣  GENERATION PIPELINE (Future)
    ├── Prompt Construction                 ← Langfuse: prompt versioning
    ├── LLM Generation (Claude/OpenAI)      ← Langfuse: trace LLM + OTEL: system metrics
    └── Answer Formatting                   ← Redis: cache responses (TTL: 5min)
    📈 Langfuse: Monitor generation quality
    🔬 RAGAS: Evaluate answer quality

4️⃣  OBSERVABILITY LAYER (Always On)
    ├── OpenTelemetry → Prometheus/Grafana  (CPU, RAM, I/O, network)
    ├── Langfuse → Trace Analytics          (LLM calls, costs, latency)
    ├── MLflow → Model Registry             (staging → production workflow)
    └── Redis → Cache Metrics               (hit_rate, saved_cost_usd)
```

---

## 🎯 Integration Strategy

### 1. MLflow: Experiment Tracking (Development Phase)

**Purpose**: Compare different pipeline configurations

#### What to Track

| Component | Parameters | Metrics | Artifacts |
|-----------|-----------|---------|-----------|
| **Chunking** | `chunk_size`, `overlap`, `min_size`, `max_size` | Chunks created, avg size | chunk_distribution.json |
| **Contextualization** | `model`, `temperature`, `prompt_version` | LLM cost, latency | context_samples.json |
| **Embeddings** | `model_name`, `batch_size`, `dimension` | Embedding time | embedding_config.json |
| **Retrieval** | `top_k`, `score_threshold`, `rerank_type` | Recall@K, Precision@K, NDCG@K, Latency | search_results.json |

#### Experiments to Run

```python
# Experiment 1: Chunking Strategies
experiments = [
    {"name": "small_chunks", "chunk_size": 400, "overlap": 100},
    {"name": "medium_chunks", "chunk_size": 600, "overlap": 150},
    {"name": "large_chunks", "chunk_size": 800, "overlap": 200},
]

# Experiment 2: Search Engines
experiments = [
    {"name": "baseline", "engine": "baseline"},
    {"name": "hybrid_rrf", "engine": "hybrid_rrf"},
    {"name": "dbsf_colbert", "engine": "dbsf_colbert"},
]

# Experiment 3: Context vs No Context
experiments = [
    {"name": "with_context", "enable_contextualization": True},
    {"name": "without_context", "enable_contextualization": False},
]
```

#### MLflow UI Structure

```
MLflow Experiments (http://localhost:5000)
├── contextual_rag_ingestion
│   ├── Run: pymupdf_small_chunks_20251030
│   ├── Run: pymupdf_medium_chunks_20251030
│   └── Run: docling_hybrid_20251030
├── contextual_rag_retrieval
│   ├── Run: baseline_eval_20251030
│   ├── Run: hybrid_rrf_eval_20251030
│   └── Run: dbsf_colbert_eval_20251030
└── contextual_rag_ab_tests
    ├── Run: context_vs_no_context_20251030
    └── Run: bge_m3_vs_bge_m3_mini_20251030
```

---

### 2. Langfuse: Production Observability (Real-time Monitoring)

**Purpose**: Monitor every request in production

#### What to Trace

**Ingestion Phase:**
```python
@observe(name="contextualize_chunk")
async def contextualize_chunk(chunk_text, document_name):
    # Langfuse automatically captures:
    # - Input: chunk_text + document_name
    # - Output: contextualized_text + metadata
    # - Latency: time taken
    # - Tokens: input/output tokens
    # - Cost: calculated from tokens

    context, metadata = await contextualizer.situate_context(
        chunk_text=chunk_text,
        document_name=document_name
    )
    return context, metadata
```

**Query Phase:**
```python
@observe(name="rag_query", as_type="agent")
async def rag_query(query: str, user_id: str):
    langfuse = get_client()

    # Set trace-level metadata
    langfuse.update_current_trace(
        user_id=user_id,
        session_id=f"session_{user_id}",
        tags=["retrieval", "production"],
        metadata={"query_type": "legal_search"}
    )

    # Step 1: Embed query
    with langfuse.start_as_current_span(name="embed_query") as span:
        query_embedding = embed(query)
        span.update(input=query, output_size=len(query_embedding))

    # Step 2: Search
    with langfuse.start_as_current_span(name="vector_search") as span:
        results = search_engine.search(query_embedding, top_k=10)
        span.update(
            input={"embedding": "...", "top_k": 10},
            output={"results_count": len(results)},
            metadata={"engine": "dbsf_colbert"}
        )

    # Step 3: Generate answer (future)
    @observe(as_type="generation")
    async def generate_answer(query, context):
        response = await llm.generate(query, context)
        return response

    answer = await generate_answer(query, results)

    # Update final trace
    langfuse.update_current_trace(
        input={"query": query},
        output={"answer": answer, "sources": results}
    )

    return answer
```

#### Langfuse Dashboard Insights

```
Langfuse UI (http://localhost:3001)
├── Traces (Real-time)
│   ├── [2025-10-30 14:23:45] rag_query: "Стаття 121 УК" → 420ms, $0.003
│   ├── [2025-10-30 14:24:12] rag_query: "Громадянський кодекс" → 380ms, $0.002
│   └── [2025-10-30 14:25:30] rag_query: "Конституція України" → 450ms, $0.004
├── Analytics
│   ├── Average latency: 416ms
│   ├── Daily cost: $2.45
│   ├── Tokens used: 125,430 tokens
│   └── Error rate: 0.2%
├── Sessions
│   ├── user_123: 15 queries, 6.2s total
│   └── user_456: 8 queries, 3.1s total
└── Prompts (Version Management)
    ├── contextualization_prompt_v1.0
    └── contextualization_prompt_v1.1
```

---

## ⚠️ Production Requirements: Must-Have vs Should-Have

### 🚨 Must-Have (Blockers for Production)

1. **Quality Evaluation Norms** ← RAGAS/Giskard offline + online
   - Golden test set (100-300 queries) with ground truth
   - Nightly RAGAS runs → MLflow
   - Acceptance thresholds: Faithfulness ≥ 0.85, Context Precision ≥ 0.80, Context Recall ≥ 0.90

2. **Formal KPI and Acceptance Criteria** per Phase
   - Week 1: Baseline established, thresholds set
   - Week 2: Cache hit_rate ≥ 30%, latency P95 ≤ 500ms
   - Week 3: Model Registry live, Qdrant restore tested

3. **OpenTelemetry Integration** (system metrics, not just LLM)
   - OTEL → Tempo/Grafana/Prometheus
   - Trace latency by steps: embed/search/rerank/generate
   - Metrics: CPU, RAM, I/O, network

4. **Cache Policies** (Redis with versioning)
   - Embedding cache: `index_v{version}_{query_hash}`, TTL 30-90 days
   - Response cache: `response_v{version}_{query_hash}`, TTL 5-60 min
   - Metrics: hit_rate by layers, evictions, saved_cost_usd

5. **Qdrant Backups** (snapshot/restore)
   - Nightly snapshots with rotation (keep last 7 days)
   - Test restore procedure monthly
   - Document recovery time objective (RTO)

6. **Data & Model Governance**
   - MLflow Model Registry: Staging → Production workflow
   - PII redaction policies (remove personal data from logs)
   - Config versioning with semantic versioning (v1.0.0)

7. **Security**
   - Budget limits per LLM provider (daily: $10, monthly: $300)
   - Secret rotation: API keys every 90 days
   - Alert when 80% budget reached

### ✅ Should-Have (Nice to Have)

1. A/B testing framework with statistical significance tests
2. User feedback collection for online quality metrics
3. Prompt versioning in Langfuse with rollback
4. Multi-model support (GPT-4o, Claude-3.5-Sonnet, Gemini-1.5-Pro)
5. Cost attribution by user/tenant

### ❌ Anti-Patterns to Avoid

1. **Blind A/B Tests** ← Run tests without baseline or acceptance criteria
2. **Cache Without Versions** ← Cache key must include config/index version
3. **Missing Baseline** ← Always establish baseline before optimization
4. **No Quality Gates** ← Don't deploy without RAGAS regression tests
5. **LLM-Only Observability** ← Must track system metrics (OTEL)
6. **No DR Plan** ← Qdrant data loss = complete reingestion (hours/days)

---

## 🚀 Implementation Roadmap (Production-Ready)

### Week 1: MLflow + RAGAS Baseline + Golden Test Set

**Goal**: Establish quality baseline with formal acceptance criteria

#### 🎯 Acceptance Criteria

```
✅ Golden test set created (100-300 queries) with ground truth
✅ RAGAS nightly runs automated → MLflow
✅ Baseline metrics measured:
   - Faithfulness ≥ 0.85
   - Context Precision ≥ 0.80
   - Context Recall ≥ 0.90
   - Latency P95 ≤ 500ms
   - Cost per 1000 queries ≤ $3
✅ MLflow experiment tracking for ingestion + retrieval
✅ Config versioning with hashes
```

#### Step 1.1: Create Golden Test Set

**File**: `tests/data/golden_test_set.json`

```json
{
  "version": "1.0.0",
  "created": "2025-10-30",
  "document": "Кримінальний кодекс України",
  "queries": [
    {
      "id": 1,
      "query": "Яка відповідальність за шахрайство?",
      "expected_articles": [190],
      "expected_answer_contains": ["позбавлення волі", "штраф", "шахрайство"],
      "category": "crimes",
      "difficulty": "easy"
    },
    {
      "id": 2,
      "query": "Стаття 121 УК України",
      "expected_articles": [121],
      "expected_answer_contains": ["умисне тяжке тілесне ушкодження"],
      "category": "lookup",
      "difficulty": "easy"
    },
    {
      "id": 3,
      "query": "Які злочини проти власності передбачені?",
      "expected_articles": [185, 186, 187, 189, 190],
      "expected_answer_contains": ["крадіжка", "грабіж", "розбій", "шахрайство"],
      "category": "legal_concept",
      "difficulty": "medium"
    }
  ],
  "total_queries": 150,
  "categories": {
    "lookup": 50,
    "crimes": 40,
    "legal_concept": 30,
    "procedure": 20,
    "definitions": 10
  }
}
```

**Generation Script**: `src/evaluation/create_golden_set.py`

```python
"""Create golden test set for Ukrainian legal RAG."""

import json
from pathlib import Path

def create_golden_test_set():
    """
    Create 100-300 queries with ground truth.

    Categories:
    - Article lookup (50 queries): "Стаття 121 УК"
    - Crime definitions (40): "Що таке шахрайство?"
    - Legal concepts (30): "Які злочи проти власності?"
    - Procedures (20): "Як подати апеляцію?"
    - Definitions (10): "Що таке презумпція невинуватості?"
    """

    queries = []

    # Category 1: Direct article lookup (easy)
    for article in [121, 122, 123, 185, 186, 187, 189, 190]:
        queries.append({
            "id": len(queries) + 1,
            "query": f"Стаття {article} УК України",
            "expected_articles": [article],
            "category": "lookup",
            "difficulty": "easy"
        })

    # Category 2: Crime questions (medium)
    crime_queries = [
        ("Яка відповідальність за шахрайство?", [190]),
        ("Що таке розбій за УК України?", [187]),
        ("Яке покарання за крадіжку?", [185]),
    ]

    for query_text, expected in crime_queries:
        queries.append({
            "id": len(queries) + 1,
            "query": query_text,
            "expected_articles": expected,
            "category": "crimes",
            "difficulty": "medium"
        })

    # ... continue for 150-300 queries

    test_set = {
        "version": "1.0.0",
        "created": "2025-10-30",
        "document": "Кримінальний кодекс України",
        "queries": queries,
        "total_queries": len(queries)
    }

    output_path = Path("tests/data/golden_test_set.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    print(f"✅ Created golden test set: {len(queries)} queries")
    print(f"   Saved to: {output_path}")

if __name__ == "__main__":
    create_golden_test_set()
```

#### Step 1.2: RAGAS Integration for Quality Metrics

**File**: `src/evaluation/ragas_evaluation.py`

```python
"""RAGAS integration for RAG quality evaluation."""

import asyncio
import json
from pathlib import Path
from datetime import datetime

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

from src.evaluation.mlflow_integration import MLflowRAGLogger


class RAGASEvaluator:
    """Evaluate RAG quality with RAGAS metrics."""

    def __init__(self):
        """Initialize RAGAS evaluator with MLflow tracking."""
        self.mlflow_logger = MLflowRAGLogger(experiment_name="ragas_quality_baseline")

        # RAGAS metrics
        self.metrics = [
            faithfulness,         # Claims in answer are grounded in context
            context_precision,    # Retrieved chunks are relevant
            context_recall,       # Ground truth is in retrieved context
            answer_relevancy,     # Answer addresses the query
        ]

    async def evaluate_pipeline(
        self,
        rag_pipeline,
        golden_test_set_path: str = "tests/data/golden_test_set.json"
    ) -> dict:
        """
        Evaluate RAG pipeline with RAGAS metrics.

        Args:
            rag_pipeline: RAG pipeline to evaluate
            golden_test_set_path: Path to golden test set

        Returns:
            RAGAS evaluation results
        """

        # Load golden test set
        with open(golden_test_set_path, "r", encoding="utf-8") as f:
            test_set = json.load(f)

        queries = test_set["queries"][:50]  # Start with 50 queries

        print(f"📊 Running RAGAS evaluation on {len(queries)} queries...")

        # Run RAG pipeline on all queries
        results = []
        for query_data in queries:
            query = query_data["query"]

            # Get RAG response
            response = await rag_pipeline.query(query, top_k=10)

            # Format for RAGAS
            results.append({
                "question": query,
                "answer": response.get("answer", ""),  # If generation enabled
                "contexts": [r["text"] for r in response["results"][:5]],
                "ground_truth": query_data.get("expected_answer", ""),
            })

        # Convert to RAGAS dataset format
        dataset = Dataset.from_list(results)

        # Run RAGAS evaluation
        start_time = datetime.now()
        ragas_results = evaluate(dataset, metrics=self.metrics)
        eval_duration = (datetime.now() - start_time).total_seconds()

        # Extract metrics
        metrics = {
            "faithfulness": ragas_results["faithfulness"],
            "context_precision": ragas_results["context_precision"],
            "context_recall": ragas_results["context_recall"],
            "answer_relevancy": ragas_results["answer_relevancy"],
            "eval_duration_seconds": eval_duration,
            "queries_evaluated": len(queries),
        }

        print("\n📈 RAGAS Results:")
        print(f"   Faithfulness:       {metrics['faithfulness']:.3f} (target: ≥ 0.85)")
        print(f"   Context Precision:  {metrics['context_precision']:.3f} (target: ≥ 0.80)")
        print(f"   Context Recall:     {metrics['context_recall']:.3f} (target: ≥ 0.90)")
        print(f"   Answer Relevancy:   {metrics['answer_relevancy']:.3f} (target: ≥ 0.80)")

        # Log to MLflow
        run_name = f"ragas_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with self.mlflow_logger.start_run(
            run_name=run_name,
            tags={"evaluation_type": "ragas", "dataset": "golden_set_v1.0"}
        ):
            self.mlflow_logger.log_metrics(metrics)

            # Log detailed results
            self.mlflow_logger.log_dict_artifact(
                {"results": results, "metrics": metrics},
                "ragas_evaluation.json",
                artifact_path="ragas"
            )

            print(f"\n📊 MLflow run: {self.mlflow_logger.get_run_url()}")

        # Check acceptance criteria
        acceptance_passed = (
            metrics["faithfulness"] >= 0.85
            and metrics["context_precision"] >= 0.80
            and metrics["context_recall"] >= 0.90
        )

        if acceptance_passed:
            print("\n✅ ACCEPTANCE CRITERIA: PASSED")
        else:
            print("\n❌ ACCEPTANCE CRITERIA: FAILED")
            print("   → Needs optimization before production")

        return metrics


async def run_nightly_ragas_evaluation():
    """Run RAGAS evaluation nightly (cron job)."""
    from src.core.rag_pipeline import RAGPipeline

    evaluator = RAGASEvaluator()
    pipeline = RAGPipeline()

    metrics = await evaluator.evaluate_pipeline(pipeline)

    # Alert if metrics drop below baseline
    if metrics["faithfulness"] < 0.85:
        print("🚨 ALERT: Faithfulness dropped below 0.85")
        # Send alert (email, Slack, etc.)

    return metrics


if __name__ == "__main__":
    asyncio.run(run_nightly_ragas_evaluation())
```

**Cron Job** (`crontab -e`):

```bash
# Run RAGAS evaluation nightly at 2 AM
0 2 * * * cd /home/admin/contextual_rag && source venv/bin/activate && python src/evaluation/ragas_evaluation.py >> logs/ragas_nightly.log 2>&1
```

#### Step 1.3: A/B Testing Framework

**New File**: `src/evaluation/mlflow_experiments.py`

```python
"""MLflow-powered A/B testing framework."""

import mlflow
from src.evaluation.mlflow_integration import MLflowRAGLogger

class RAGExperimentRunner:
    """Run structured experiments with MLflow tracking."""

    def __init__(self, experiment_name: str):
        self.logger = MLflowRAGLogger(experiment_name=experiment_name)

    async def run_ab_test(
        self,
        test_name: str,
        variant_a: dict,
        variant_b: dict,
        test_queries: list
    ):
        """Run A/B test between two variants."""

        print(f"🧪 Running A/B test: {test_name}")

        # Variant A
        with self.logger.start_run(
            run_name=f"{test_name}_variant_a",
            tags={"test": test_name, "variant": "A"}
        ):
            results_a = await self._run_variant(variant_a, test_queries)
            self.logger.log_config(variant_a, prefix="variant_a.")
            self.logger.log_metrics(results_a)

        # Variant B
        with self.logger.start_run(
            run_name=f"{test_name}_variant_b",
            tags={"test": test_name, "variant": "B"}
        ):
            results_b = await self._run_variant(variant_b, test_queries)
            self.logger.log_config(variant_b, prefix="variant_b.")
            self.logger.log_metrics(results_b)

        # Compare
        winner = "A" if results_a["recall_at_1"] > results_b["recall_at_1"] else "B"

        print(f"\n📊 A/B Test Results: {test_name}")
        print(f"   Variant A: Recall@1={results_a['recall_at_1']:.3f}")
        print(f"   Variant B: Recall@1={results_b['recall_at_1']:.3f}")
        print(f"   Winner: Variant {winner}")

        return {"variant_a": results_a, "variant_b": results_b, "winner": winner}

# Example usage
runner = RAGExperimentRunner(experiment_name="contextual_rag_ab_tests")

# Test 1: Context vs No Context
await runner.run_ab_test(
    test_name="context_vs_no_context",
    variant_a={"enable_contextualization": True},
    variant_b={"enable_contextualization": False},
    test_queries=test_queries
)

# Test 2: Small vs Large Chunks
await runner.run_ab_test(
    test_name="chunk_size_comparison",
    variant_a={"chunk_size": 400, "overlap": 100},
    variant_b={"chunk_size": 800, "overlap": 200},
    test_queries=test_queries
)
```

---

### Week 2: Langfuse + OpenTelemetry + Redis Cache

**Goal**: Production observability with system metrics and semantic caching

#### 🎯 Acceptance Criteria

```
✅ Langfuse tracing for all LLM calls (contextualization + generation)
✅ OpenTelemetry integration → Prometheus/Grafana/Tempo
✅ System metrics tracked: CPU, RAM, I/O, network
✅ Latency by steps: embed/search/rerank/generate (P50, P95, P99)
✅ Redis semantic cache implemented:
   - Embedding cache: TTL 30 days, key = index_v{version}_{query_hash}
   - Response cache: TTL 5-60 min, key = response_v{version}_{query_hash}
✅ Cache metrics dashboard:
   - hit_rate ≥ 30% (after warm-up)
   - saved_cost_usd tracked
   - evictions monitored
✅ Dashboards live in Grafana with alerts
```

#### Step 2.1: Ingestion Observability

**File**: `legacy/contextualize_zai_async.py`

```python
from langfuse import observe, get_client

class ContextualRetrievalZAIAsync:

    @observe(as_type="generation")
    async def situate_context_with_metadata(
        self,
        chunk_text: str,
        document_name: str = "Цивільний кодекс України"
    ) -> tuple[str, dict]:
        """
        Generate context for chunk with Langfuse tracing.

        Langfuse automatically captures:
        - Input: chunk_text + document_name
        - Output: context_text + metadata
        - Latency: time taken
        - Tokens: input/output (if available)
        """

        langfuse = get_client()

        # Update generation metadata
        langfuse.update_current_generation(
            name="contextualize_chunk",
            model="glm-4.6",
            model_parameters={
                "temperature": 0.1,
                "max_tokens": 512,
            },
            metadata={
                "document": document_name,
                "chunk_length": len(chunk_text),
            }
        )

        async with self.semaphore:
            # Make LLM request
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    self.api_url,
                    json={"messages": messages, "model": "glm-4.6"},
                    headers=headers
                )
                result = await response.json()

            # Parse response
            context_text, metadata = self._parse_response(result, chunk_text)

            # Update with usage info
            if "usage" in result:
                langfuse.update_current_generation(
                    usage={
                        "input": result["usage"]["prompt_tokens"],
                        "output": result["usage"]["completion_tokens"],
                    }
                )

            return context_text, metadata
```

#### Step 2.2: Retrieval Observability

**File**: `src/retrieval/search_engines.py`

```python
from langfuse import observe, get_client

class DBSFColBERTSearchEngine(BaseSearchEngine):

    @observe(name="vector_search", as_type="tool")
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[SearchResult]:
        """Search with Langfuse tracing."""

        langfuse = get_client()

        # Update span metadata
        langfuse.update_current_span(
            metadata={
                "engine": "dbsf_colbert",
                "top_k": top_k,
                "score_threshold": score_threshold,
                "embedding_dim": len(query_embedding),
            }
        )

        # Perform search
        start_time = time.time()
        results = self.client.search(
            collection_name=self.settings.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=score_threshold or 0.3,
        )
        search_latency_ms = (time.time() - start_time) * 1000

        # Log metrics
        langfuse.update_current_span(
            output={
                "results_count": len(results),
                "top_score": results[0].score if results else 0,
                "latency_ms": search_latency_ms,
            }
        )

        return [self._convert_result(r) for r in results]
```

#### Step 2.3: End-to-End Query Tracing

**New File**: `src/core/rag_pipeline_observed.py`

```python
"""RAG Pipeline with full Langfuse observability."""

from langfuse import observe, get_client

class ObservedRAGPipeline:
    """RAG Pipeline with Langfuse tracing."""

    @observe(name="rag_query", as_type="agent")
    async def query(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 10
    ) -> dict:
        """
        Execute RAG query with full observability.

        Creates nested trace:
        - rag_query (agent)
          ├── embed_query (tool)
          ├── vector_search (tool)
          ├── rerank_results (tool)
          └── generate_answer (generation) [future]
        """

        langfuse = get_client()

        # Set trace-level context
        langfuse.update_current_trace(
            name="rag_query",
            user_id=user_id or "anonymous",
            session_id=session_id or f"session_{uuid.uuid4().hex[:8]}",
            tags=["retrieval", "production", "legal_search"],
            metadata={
                "query_length": len(query),
                "top_k": top_k,
            }
        )

        # Step 1: Embed query
        query_embedding = await self._embed_query(query)

        # Step 2: Search
        results = await self._search(query_embedding, top_k)

        # Step 3: Format response
        response = {
            "query": query,
            "results": results,
            "results_count": len(results),
        }

        # Update trace output
        langfuse.update_current_trace(
            input={"query": query, "top_k": top_k},
            output=response
        )

        return response

    @observe(as_type="tool")
    async def _embed_query(self, query: str) -> list[float]:
        """Embed query with tracing."""
        # BGE-M3 embedding call
        embedding = await self.embedder.embed(query)

        langfuse = get_client()
        langfuse.update_current_span(
            input={"query": query},
            output={"embedding_dim": len(embedding)},
            metadata={"model": "bge-m3"}
        )

        return embedding

    @observe(as_type="tool")
    async def _search(self, query_embedding: list[float], top_k: int) -> list[dict]:
        """Search with tracing."""
        results = self.search_engine.search(query_embedding, top_k=top_k)

        langfuse = get_client()
        langfuse.update_current_span(
            output={"results_count": len(results)},
            metadata={"engine": self.search_engine.get_name()}
        )

        return [r.to_dict() for r in results]
```

---

### Phase 3: Integration & Dashboards (Week 3)

#### Step 3.1: Combined Experiment + Monitoring

**New File**: `src/evaluation/mlflow_langfuse_integration.py`

```python
"""
Combined MLflow + Langfuse integration.

Best practice 2025:
- MLflow for batch evaluation experiments
- Langfuse for individual query tracing
- Cross-reference between platforms via run IDs
"""

import mlflow
from langfuse import observe, get_client
from src.evaluation.mlflow_integration import MLflowRAGLogger

class UnifiedObservability:
    """Combined MLflow + Langfuse tracking."""

    def __init__(self, experiment_name: str):
        self.mlflow_logger = MLflowRAGLogger(experiment_name=experiment_name)
        self.langfuse = get_client()

    @observe(name="evaluate_rag_system")
    async def run_evaluation(
        self,
        test_queries: list,
        search_engine_config: dict
    ):
        """
        Run evaluation with both MLflow and Langfuse.

        - MLflow tracks: aggregate metrics, configs, artifacts
        - Langfuse traces: individual query executions
        """

        # Start MLflow run
        run_name = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with self.mlflow_logger.start_run(run_name=run_name):
            # Log config to MLflow
            self.mlflow_logger.log_config(search_engine_config, prefix="search.")

            # Add MLflow run ID to Langfuse trace
            mlflow_run_id = mlflow.active_run().info.run_id
            self.langfuse.update_current_trace(
                metadata={
                    "mlflow_run_id": mlflow_run_id,
                    "mlflow_experiment": self.mlflow_logger.experiment_name,
                }
            )

            # Run evaluation (each query traced by Langfuse)
            results = []
            for query_data in test_queries:
                result = await self._evaluate_query(
                    query_data["query"],
                    query_data["expected_article"],
                    langfuse_tags=[f"mlflow_run:{mlflow_run_id}"]
                )
                results.append(result)

            # Aggregate metrics → MLflow
            metrics = self._compute_metrics(results)
            self.mlflow_logger.log_metrics(metrics)

            print(f"📊 MLflow: {self.mlflow_logger.get_run_url()}")
            print(f"📈 Langfuse: http://localhost:3001")
            print(f"   Filter by tag: mlflow_run:{mlflow_run_id}")

            return metrics

    @observe()
    async def _evaluate_query(
        self,
        query: str,
        expected_article: int,
        langfuse_tags: list[str]
    ):
        """Evaluate single query (traced by Langfuse)."""

        # Add tags to link to MLflow run
        self.langfuse.update_current_trace(tags=langfuse_tags)

        # Execute query
        results = await self.rag_pipeline.query(query)

        # Check if correct
        correct = any(r["article_number"] == expected_article for r in results[:1])

        return {
            "query": query,
            "expected": expected_article,
            "results": results,
            "correct": correct,
        }
```

#### Step 3.2: Monitoring Dashboard Configuration

**File**: `docs/monitoring/LANGFUSE_DASHBOARDS.md`

```markdown
# Langfuse Dashboards Configuration

## Dashboard 1: Query Performance

**Metrics:**
- Average latency (P50, P95, P99)
- Queries per minute
- Error rate
- Cost per query

**Filters:**
- By user
- By session
- By date range
- By search engine

**Alerts:**
- Latency > 1000ms
- Error rate > 1%
- Cost per query > $0.01

## Dashboard 2: LLM Usage

**Metrics:**
- Token usage (input/output)
- Cost breakdown (by model)
- Average tokens per request
- Cost trends over time

**Filters:**
- By model (glm-4.6, gpt-4o, claude-3.5-sonnet)
- By operation (contextualization, generation)

## Dashboard 3: User Analytics

**Metrics:**
- Active users
- Queries per user
- Session duration
- User satisfaction (via feedback)

**Filters:**
- By user cohort
- By time period
```

---

## 📊 Success Metrics

### MLflow Success Metrics

```
After Phase 1 completion:
- ✅ All ingestion runs tracked with config hash
- ✅ A/B test framework with automatic comparison
- ✅ 3+ experiments run and documented
- ✅ Retrieval metrics tracked (Recall, NDCG, Latency)
```

### Langfuse Success Metrics

```
After Phase 2 completion:
- ✅ 100% LLM calls traced (contextualization)
- ✅ End-to-end query tracing (embed → search → generate)
- ✅ Cost tracking per query (<$0.005 target)
- ✅ Latency monitoring (P95 < 500ms target)
```

---

## 🎓 Best Practices 2025

### 1. **Separation of Concerns**

```
❌ DON'T: Use MLflow for production monitoring
❌ DON'T: Use Langfuse for batch experiments

✅ DO: MLflow for research/experiments
✅ DO: Langfuse for production/debugging
```

### 2. **Cross-Platform Linking**

```python
# Link Langfuse traces to MLflow runs
mlflow_run_id = mlflow.active_run().info.run_id

langfuse.update_current_trace(
    tags=[f"mlflow_run:{mlflow_run_id}"],
    metadata={"mlflow_experiment": experiment_name}
)
```

### 3. **Structured Experiments**

```python
# Always use structured naming
run_name = f"{component}_{variant}_{timestamp}"
# Example: "retrieval_dbsf_colbert_20251030_142315"

# Always tag runs
tags = {
    "component": "retrieval",
    "variant": "dbsf_colbert",
    "environment": "development",
}
```

### 4. **Cost Optimization**

```python
# Track costs in Langfuse
@observe(as_type="generation")
async def llm_call():
    # Langfuse automatically calculates cost
    # based on model + tokens used
    pass

# Set budget alerts in Langfuse UI:
# - Daily budget: $10
# - Alert when 80% reached
```

### 5. **Progressive Rollout**

```
Week 1: MLflow for ingestion + retrieval experiments
Week 2: Langfuse for contextualization tracing
Week 3: End-to-end integration + dashboards
Week 4: Production deployment + monitoring
```

---

## 🔧 Quick Start Commands

### MLflow

```bash
# View experiments
open http://localhost:5000

# Run experiment
python src/evaluation/mlflow_experiments.py

# Compare runs
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

### Langfuse

```bash
# View traces
open http://localhost:3001

# Check current traces
curl http://localhost:3001/api/public/traces

# Monitor costs
# UI → Analytics → Cost Tracking
```

---

## 📚 Resources

### Documentation
- MLflow: https://mlflow.org/docs/latest/
- Langfuse: https://langfuse.com/docs
- Best Practices 2025: This document

### Internal Links
- MLflow Integration: `src/evaluation/mlflow_integration.py`
- Langfuse Integration: `src/evaluation/langfuse_integration.py`
- Monitoring Setup: `docs/monitoring/MONITORING-QUICK-REFERENCE.md`

---

## 🎯 Next Steps

**Your action items:**

1. **Review this plan** - понять архитектуру интеграции
2. **Phase 1** - начать с MLflow experiment tracking
3. **Phase 2** - добавить Langfuse observability
4. **Phase 3** - интегрировать оба сервиса

**Questions to answer:**
- Какие эксперименты хочешь запустить первыми?
- Нужно ли сразу полное трассирование или постепенно?
- Какие метрики наиболее важны для мониторинга?

---

**Last Updated**: 2025-10-30
**Status**: Ready for Implementation
**Estimated Time**: 3 weeks
