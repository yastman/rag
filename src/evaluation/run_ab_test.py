#!/usr/bin/env python3
"""
Run A/B test comparing search engines: Baseline vs Hybrid vs DBSF+ColBERT.

Search Engines:
1. Baseline: Dense-only (BGE-M3 dense vectors)
2. Hybrid: Dense + Sparse with RRF fusion (ColBERT disabled)
3. DBSF+ColBERT: Dense + Sparse → DBSF fusion → ColBERT rerank (Qdrant 2025 Best Practice)

Steps:
1. Load test queries
2. Initialize all search engines
3. Run searches for all queries
4. Evaluate results
5. Generate comparison reports
"""

import json
import time
from datetime import datetime

from src.evaluation.evaluator import SearchEvaluator
from src.evaluation.search_engines import create_search_engine


# MLflow integration (optional - gracefully handles if not available)
try:
    from mlflow_integration import MLflowRAGLogger

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    print("⚠️  MLflow integration not available (install mlflow to enable)")


def run_ab_test(
    queries_file: str,
    ground_truth_file: str,
    collection_name: str,
    output_dir: str = "evaluation/reports",
):
    """
    Run complete A/B test.

    Args:
        queries_file: Path to queries_testset.json
        ground_truth_file: Path to ground_truth_articles.json
        collection_name: Qdrant collection name
        output_dir: Directory to save reports
    """
    print("=" * 80)
    print("🔬 A/B TEST: Baseline vs Hybrid Search")
    print("=" * 80)
    print()

    # Load test queries
    print("📂 Loading test queries...")
    with open(queries_file, encoding="utf-8") as f:
        queries = json.load(f)
    print(f"   Loaded {len(queries)} test queries")

    if not queries:
        print("⚠️  No queries found. Aborting A/B test.")
        return {"baseline": {}, "hybrid": {}, "dbsf_colbert": {}, "comparisons": {}, "reports": {}}

    print()

    # Initialize embedding model
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError as e:
        raise ImportError(
            "FlagEmbedding is not installed. Install ml-local extra: uv sync --extra ml-local"
        ) from e

    print("🤖 Loading BGE-M3 embedding model...")
    start_time = time.time()
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    load_time = time.time() - start_time
    print(f"   ✓ Model loaded in {load_time:.2f}s")
    print()

    # Initialize search engines
    print("🔧 Initializing search engines...")
    baseline_engine = create_search_engine("baseline", collection_name, model)
    hybrid_engine = create_search_engine("hybrid", collection_name, model)
    dbsf_colbert_engine = create_search_engine("dbsf_colbert", collection_name, model)
    print("   ✓ Baseline engine (dense-only) ready")
    print("   ✓ Hybrid engine (dense+sparse RRF, ColBERT disabled) ready")
    print("   ✓ DBSF+ColBERT engine (dense+sparse DBSF → ColBERT rerank) ready")
    print()

    # Initialize evaluator
    evaluator = SearchEvaluator(ground_truth_file)

    # Run baseline search
    print("=" * 80)
    print("🔍 PHASE 1: Baseline Search (Dense-only)")
    print("=" * 80)
    baseline_results_map = {}
    baseline_start = time.time()

    for i, query in enumerate(queries, 1):
        query_text = query["query"]
        try:
            results = baseline_engine.search(query_text, top_k=10)
            baseline_results_map[query_text] = results
            print(f"[{i}/{len(queries)}] ✓ {query_text[:60]}...")
        except Exception as e:
            print(f"[{i}/{len(queries)}] ✗ ERROR: {e}")
            baseline_results_map[query_text] = []

    baseline_time = time.time() - baseline_start
    print(f"\n⏱️  Baseline search completed in {baseline_time:.2f}s")
    print(f"   Average: {baseline_time / len(queries):.3f}s per query")
    print()

    # Run hybrid search
    print("=" * 80)
    print("🔍 PHASE 2: Hybrid Search (Dense+Sparse RRF, ColBERT disabled)")
    print("=" * 80)
    hybrid_results_map = {}
    hybrid_start = time.time()

    for i, query in enumerate(queries, 1):
        query_text = query["query"]
        try:
            results = hybrid_engine.search(query_text, top_k=10)
            hybrid_results_map[query_text] = results
            print(f"[{i}/{len(queries)}] ✓ {query_text[:60]}...")
        except Exception as e:
            print(f"[{i}/{len(queries)}] ✗ ERROR: {e}")
            hybrid_results_map[query_text] = []

    hybrid_time = time.time() - hybrid_start
    print(f"\n⏱️  Hybrid search completed in {hybrid_time:.2f}s")
    print(f"   Average: {hybrid_time / len(queries):.3f}s per query")
    print()

    # Run DBSF+ColBERT search
    print("=" * 80)
    print("🔍 PHASE 3: DBSF+ColBERT Search (Dense+Sparse DBSF → ColBERT rerank)")
    print("=" * 80)
    dbsf_results_map = {}
    dbsf_start = time.time()

    for i, query in enumerate(queries, 1):
        query_text = query["query"]
        try:
            results = dbsf_colbert_engine.search(query_text, top_k=10)
            dbsf_results_map[query_text] = results
            print(f"[{i}/{len(queries)}] ✓ {query_text[:60]}...")
        except Exception as e:
            print(f"[{i}/{len(queries)}] ✗ ERROR: {e}")
            dbsf_results_map[query_text] = []

    dbsf_time = time.time() - dbsf_start
    print(f"\n⏱️  DBSF+ColBERT search completed in {dbsf_time:.2f}s")
    print(f"   Average: {dbsf_time / len(queries):.3f}s per query")
    print()

    # Evaluate baseline
    print("=" * 80)
    print("📊 PHASE 4: Evaluating Baseline Results")
    print("=" * 80)
    baseline_eval = evaluator.evaluate_queries(queries, baseline_results_map)
    print_metrics(baseline_eval["metrics"])
    print()

    # Evaluate hybrid
    print("=" * 80)
    print("📊 PHASE 5: Evaluating Hybrid Results")
    print("=" * 80)
    hybrid_eval = evaluator.evaluate_queries(queries, hybrid_results_map)
    print_metrics(hybrid_eval["metrics"])
    print()

    # Evaluate DBSF+ColBERT
    print("=" * 80)
    print("📊 PHASE 6: Evaluating DBSF+ColBERT Results")
    print("=" * 80)
    dbsf_eval = evaluator.evaluate_queries(queries, dbsf_results_map)
    print_metrics(dbsf_eval["metrics"])
    print()

    # Compare all engines
    print("=" * 80)
    print("📈 PHASE 7: Statistical Comparison")
    print("=" * 80)

    # Baseline vs Hybrid
    print("\n🔸 Baseline vs Hybrid (RRF):")
    print("-" * 80)
    comparison_hybrid = evaluator.compare_engines(baseline_eval, hybrid_eval)
    print_comparison(comparison_hybrid)

    # Baseline vs DBSF+ColBERT
    print("\n🔸 Baseline vs DBSF+ColBERT:")
    print("-" * 80)
    comparison_dbsf = evaluator.compare_engines(baseline_eval, dbsf_eval)
    print_comparison(comparison_dbsf)

    # Hybrid vs DBSF+ColBERT
    print("\n🔸 Hybrid (RRF) vs DBSF+ColBERT:")
    print("-" * 80)
    comparison_hybrid_dbsf = evaluator.compare_engines(hybrid_eval, dbsf_eval)
    print_comparison(comparison_hybrid_dbsf)
    print()

    # Save results
    print("=" * 80)
    print("💾 PHASE 8: Saving Results")
    print("=" * 80)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save baseline results
    baseline_report_file = f"{output_dir}/baseline_results_{timestamp}.json"
    with open(baseline_report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "engine": "baseline",
                "collection": collection_name,
                "total_queries": len(queries),
                "search_time_total": baseline_time,
                "search_time_avg": baseline_time / len(queries),
                "evaluation": baseline_eval,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"   ✓ Baseline report: {baseline_report_file}")

    # Save hybrid results
    hybrid_report_file = f"{output_dir}/hybrid_results_{timestamp}.json"
    with open(hybrid_report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "engine": "hybrid",
                "collection": collection_name,
                "total_queries": len(queries),
                "search_time_total": hybrid_time,
                "search_time_avg": hybrid_time / len(queries),
                "evaluation": hybrid_eval,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"   ✓ Hybrid report: {hybrid_report_file}")

    # Save DBSF+ColBERT results
    dbsf_report_file = f"{output_dir}/dbsf_colbert_results_{timestamp}.json"
    with open(dbsf_report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "engine": "dbsf_colbert",
                "collection": collection_name,
                "total_queries": len(queries),
                "search_time_total": dbsf_time,
                "search_time_avg": dbsf_time / len(queries),
                "evaluation": dbsf_eval,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"   ✓ DBSF+ColBERT report: {dbsf_report_file}")

    # Save comparison (convert numpy types to Python types for JSON)
    comparison_report_file = f"{output_dir}/comparison_report_{timestamp}.json"

    def convert_numpy(obj):
        """Convert numpy types to Python types for JSON serialization."""
        import numpy as np

        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        if isinstance(obj, dict):
            return {k: convert_numpy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        return obj

    comparison_hybrid_clean = convert_numpy(comparison_hybrid)
    comparison_dbsf_clean = convert_numpy(comparison_dbsf)
    comparison_hybrid_dbsf_clean = convert_numpy(comparison_hybrid_dbsf)

    with open(comparison_report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "collection": collection_name,
                "total_queries": len(queries),
                "search_times": {
                    "baseline": baseline_time,
                    "hybrid": hybrid_time,
                    "dbsf_colbert": dbsf_time,
                },
                "comparisons": {
                    "baseline_vs_hybrid": comparison_hybrid_clean,
                    "baseline_vs_dbsf_colbert": comparison_dbsf_clean,
                    "hybrid_vs_dbsf_colbert": comparison_hybrid_dbsf_clean,
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"   ✓ Comparison report: {comparison_report_file}")

    # Generate human-readable markdown report
    markdown_file = f"{output_dir}/AB_TEST_REPORT_{timestamp}.md"
    generate_markdown_report(
        markdown_file,
        {
            "timestamp": timestamp,
            "collection": collection_name,
            "total_queries": len(queries),
            "baseline_time": baseline_time,
            "hybrid_time": hybrid_time,
            "dbsf_time": dbsf_time,
            "baseline_eval": baseline_eval,
            "hybrid_eval": hybrid_eval,
            "dbsf_eval": dbsf_eval,
            "comparison_hybrid": comparison_hybrid,
            "comparison_dbsf": comparison_dbsf,
            "comparison_hybrid_dbsf": comparison_hybrid_dbsf,
        },
    )
    print(f"   ✓ Markdown report: {markdown_file}")
    print()

    # Log to MLflow (if available)
    if MLFLOW_AVAILABLE:
        print("=" * 80)
        print("📊 PHASE 9: Logging to MLflow")
        print("=" * 80)
        try:
            logger = MLflowRAGLogger(experiment_name="contextual_rag_ab_tests")

            # Create run name from timestamp
            run_name = f"ab_test_{timestamp}"

            with logger.start_run(
                run_name=run_name, tags={"type": "ab_test", "collection": collection_name}
            ):
                # Log common config
                common_config = {
                    "collection": collection_name,
                    "total_queries": len(queries),
                    "model": "BAAI/bge-m3",
                    "model_load_time_sec": load_time,
                }
                logger.log_config(common_config, prefix="experiment.")

                # Log baseline metrics
                baseline_metrics = {
                    "baseline.recall_at_1": baseline_eval["metrics"].get("recall@1", 0),
                    "baseline.recall_at_10": baseline_eval["metrics"].get("recall@10", 0),
                    "baseline.ndcg_at_10": baseline_eval["metrics"].get("ndcg@10", 0),
                    "baseline.mrr": baseline_eval["metrics"].get("mrr", 0),
                    "baseline.failure_rate": baseline_eval["metrics"].get("failure_rate", 0),
                    "baseline.search_time_total_sec": baseline_time,
                    "baseline.search_time_avg_sec": baseline_time / len(queries),
                }

                # Log hybrid metrics
                hybrid_metrics = {
                    "hybrid.recall_at_1": hybrid_eval["metrics"].get("recall@1", 0),
                    "hybrid.recall_at_10": hybrid_eval["metrics"].get("recall@10", 0),
                    "hybrid.ndcg_at_10": hybrid_eval["metrics"].get("ndcg@10", 0),
                    "hybrid.mrr": hybrid_eval["metrics"].get("mrr", 0),
                    "hybrid.failure_rate": hybrid_eval["metrics"].get("failure_rate", 0),
                    "hybrid.search_time_total_sec": hybrid_time,
                    "hybrid.search_time_avg_sec": hybrid_time / len(queries),
                }

                # Log DBSF+ColBERT metrics
                dbsf_metrics = {
                    "dbsf_colbert.recall_at_1": dbsf_eval["metrics"].get("recall@1", 0),
                    "dbsf_colbert.recall_at_10": dbsf_eval["metrics"].get("recall@10", 0),
                    "dbsf_colbert.ndcg_at_10": dbsf_eval["metrics"].get("ndcg@10", 0),
                    "dbsf_colbert.mrr": dbsf_eval["metrics"].get("mrr", 0),
                    "dbsf_colbert.failure_rate": dbsf_eval["metrics"].get("failure_rate", 0),
                    "dbsf_colbert.search_time_total_sec": dbsf_time,
                    "dbsf_colbert.search_time_avg_sec": dbsf_time / len(queries),
                }

                # Log comparison improvements (DBSF vs Baseline)
                improvement_metrics = {
                    "improvement.recall_at_1_pct": comparison_dbsf["improvements"]["recall@1"][
                        "relative_improvement_pct"
                    ],
                    "improvement.recall_at_10_pct": comparison_dbsf["improvements"]["recall@10"][
                        "relative_improvement_pct"
                    ],
                    "improvement.ndcg_at_10_pct": comparison_dbsf["improvements"]["ndcg@10"][
                        "relative_improvement_pct"
                    ],
                    "improvement.mrr_pct": comparison_dbsf["improvements"]["mrr"][
                        "relative_improvement_pct"
                    ],
                }

                # Log all metrics
                logger.log_metrics(
                    {**baseline_metrics, **hybrid_metrics, **dbsf_metrics, **improvement_metrics}
                )

                # Log markdown report as artifact
                try:
                    logger.log_artifact(markdown_file, artifact_path="reports")
                    print("   ✓ Logged markdown report to MLflow")
                except Exception as e:
                    print(f"   ⚠️  Could not log artifact: {e}")

                run_url = logger.get_run_url()
                print(f"   ✓ MLflow run URL: {run_url}")

        except Exception as e:
            print(f"   ⚠️  MLflow logging failed: {e}")
            print("   Continuing without MLflow logging...")

        print()

    print("=" * 80)
    print("✅ A/B TEST COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print()

    return {
        "baseline": baseline_eval,
        "hybrid": hybrid_eval,
        "dbsf_colbert": dbsf_eval,
        "comparisons": {
            "baseline_vs_hybrid": comparison_hybrid,
            "baseline_vs_dbsf_colbert": comparison_dbsf,
            "hybrid_vs_dbsf_colbert": comparison_hybrid_dbsf,
        },
        "reports": {
            "baseline": baseline_report_file,
            "hybrid": hybrid_report_file,
            "dbsf_colbert": dbsf_report_file,
            "comparison": comparison_report_file,
            "markdown": markdown_file,
        },
    }


def print_metrics(metrics: dict):
    """Print metrics in readable format."""
    print(f"   Recall@1:  {metrics.get('recall@1', 0):.4f}")
    print(f"   Recall@3:  {metrics.get('recall@3', 0):.4f}")
    print(f"   Recall@5:  {metrics.get('recall@5', 0):.4f}")
    print(f"   Recall@10: {metrics.get('recall@10', 0):.4f}")
    print(f"   MRR:       {metrics.get('mrr', 0):.4f}")
    print(f"   NDCG@10:   {metrics.get('ndcg@10', 0):.4f}")
    print(
        f"   Failure:   {metrics.get('failure_rate', 0):.4f} ({metrics.get('failure_rate', 0) * 100:.1f}%)"
    )


def print_comparison(comparison: dict):
    """Print comparison in readable format."""
    print("\n📊 Metric Improvements (Hybrid vs Baseline):")
    print("-" * 80)

    for metric, data in comparison["improvements"].items():
        baseline = data["baseline"]
        hybrid = data["hybrid"]
        improvement = data["relative_improvement_pct"]

        # Determine if higher or lower is better
        if metric == "failure_rate":
            symbol = "📉" if improvement > 0 else "📈"
        else:
            symbol = "📈" if improvement > 0 else "📉"

        print(f"   {symbol} {metric:15s}: {baseline:.4f} → {hybrid:.4f} ({improvement:+.1f}%)")

    # Statistical significance
    if "statistical_significance" in comparison:
        sig = comparison["statistical_significance"].get("recall@10", {})
        print("\n📊 Statistical Significance (Paired t-test on Recall@10):")
        print(f"   t-statistic: {sig.get('t_statistic', 0):.4f}")
        print(f"   p-value: {sig.get('p_value', 1):.6f}")
        if sig.get("significant_at_0.01"):
            print("   ✅ HIGHLY SIGNIFICANT (p < 0.01)")
        elif sig.get("significant_at_0.05"):
            print("   ✅ SIGNIFICANT (p < 0.05)")
        else:
            print("   ⚠️  NOT SIGNIFICANT (p ≥ 0.05)")


def generate_markdown_report(filename: str, data: dict):
    """Generate human-readable markdown report for 3-way comparison."""
    baseline = data["baseline_eval"]["metrics"]
    hybrid = data["hybrid_eval"]["metrics"]
    dbsf = data["dbsf_eval"]["metrics"]
    data["comparison_hybrid"]
    comp_dbsf = data["comparison_dbsf"]
    comp_hybrid_dbsf = data["comparison_hybrid_dbsf"]

    md = f"""# A/B Test Report: Baseline vs Hybrid vs DBSF+ColBERT

**Generated:** {data["timestamp"]}
**Collection:** {data["collection"]}
**Total Queries:** {data["total_queries"]}

---

## Executive Summary

### Search Performance Comparison

| Metric | Baseline | Hybrid (RRF) | DBSF+ColBERT | Best |
|--------|----------|--------------|--------------|------|
| Recall@1 | {baseline.get("recall@1", 0):.4f} | {hybrid.get("recall@1", 0):.4f} | {dbsf.get("recall@1", 0):.4f} | {"DBSF" if dbsf.get("recall@1", 0) >= max(baseline.get("recall@1", 0), hybrid.get("recall@1", 0)) else ("Hybrid" if hybrid.get("recall@1", 0) >= baseline.get("recall@1", 0) else "Baseline")} |
| Recall@10 | {baseline.get("recall@10", 0):.4f} | {hybrid.get("recall@10", 0):.4f} | {dbsf.get("recall@10", 0):.4f} | {"DBSF" if dbsf.get("recall@10", 0) >= max(baseline.get("recall@10", 0), hybrid.get("recall@10", 0)) else ("Hybrid" if hybrid.get("recall@10", 0) >= baseline.get("recall@10", 0) else "Baseline")} |
| NDCG@10 | {baseline.get("ndcg@10", 0):.4f} | {hybrid.get("ndcg@10", 0):.4f} | {dbsf.get("ndcg@10", 0):.4f} | {"DBSF" if dbsf.get("ndcg@10", 0) >= max(baseline.get("ndcg@10", 0), hybrid.get("ndcg@10", 0)) else ("Hybrid" if hybrid.get("ndcg@10", 0) >= baseline.get("ndcg@10", 0) else "Baseline")} |
| MRR | {baseline.get("mrr", 0):.4f} | {hybrid.get("mrr", 0):.4f} | {dbsf.get("mrr", 0):.4f} | {"DBSF" if dbsf.get("mrr", 0) >= max(baseline.get("mrr", 0), hybrid.get("mrr", 0)) else ("Hybrid" if hybrid.get("mrr", 0) >= baseline.get("mrr", 0) else "Baseline")} |
| Failure Rate | {baseline.get("failure_rate", 0):.4f} | {hybrid.get("failure_rate", 0):.4f} | {dbsf.get("failure_rate", 0):.4f} | {"DBSF" if dbsf.get("failure_rate", 0) <= min(baseline.get("failure_rate", 0), hybrid.get("failure_rate", 0)) else ("Hybrid" if hybrid.get("failure_rate", 0) <= baseline.get("failure_rate", 0) else "Baseline")} |

### Search Time

| Engine | Total Time | Avg per Query |
|--------|------------|---------------|
| Baseline | {data["baseline_time"]:.2f}s | {data["baseline_time"] / data["total_queries"]:.3f}s |
| Hybrid (RRF) | {data["hybrid_time"]:.2f}s | {data["hybrid_time"] / data["total_queries"]:.3f}s |
| DBSF+ColBERT | {data["dbsf_time"]:.2f}s | {data["dbsf_time"] / data["total_queries"]:.3f}s |

---

## Detailed Results

### Baseline Engine (Dense-only)

**Architecture:**
- Dense vectors only (BGE-M3 1024D INT8)
- Simple cosine similarity search

**Metrics:**
- Recall@1:  {baseline.get("recall@1", 0):.4f}
- Recall@10: {baseline.get("recall@10", 0):.4f}
- MRR:       {baseline.get("mrr", 0):.4f}
- NDCG@10:   {baseline.get("ndcg@10", 0):.4f}
- Failure:   {baseline.get("failure_rate", 0):.4f} ({baseline.get("failure_rate", 0) * 100:.1f}%)

### Hybrid Engine (Dense+Sparse RRF, ColBERT disabled)

**Architecture:**
- Dense: BGE-M3 1024D INT8 vectors
- Sparse: BM25 with IDF weighting
- Fusion: Reciprocal Rank Fusion (RRF)
- Note: ColBERT disabled in this version

**Metrics:**
- Recall@1:  {hybrid.get("recall@1", 0):.4f}
- Recall@10: {hybrid.get("recall@10", 0):.4f}
- MRR:       {hybrid.get("mrr", 0):.4f}
- NDCG@10:   {hybrid.get("ndcg@10", 0):.4f}
- Failure:   {hybrid.get("failure_rate", 0):.4f} ({hybrid.get("failure_rate", 0) * 100:.1f}%)

### DBSF+ColBERT Engine (Qdrant 2025 Best Practice)

**Architecture:**
- Stage 1: Dense + Sparse → 100 candidates each
- Stage 2: DBSF (Distribution-Based Score Fusion) combines results
- Stage 3: ColBERT multivector server-side reranking → top-10
- Score threshold: 0.3, HNSW ef: 256

**Metrics:**
- Recall@1:  {dbsf.get("recall@1", 0):.4f}
- Recall@10: {dbsf.get("recall@10", 0):.4f}
- MRR:       {dbsf.get("mrr", 0):.4f}
- NDCG@10:   {dbsf.get("ndcg@10", 0):.4f}
- Failure:   {dbsf.get("failure_rate", 0):.4f} ({dbsf.get("failure_rate", 0) * 100:.1f}%)

---

## Statistical Comparisons

### Baseline vs DBSF+ColBERT

| Metric | Improvement |
|--------|-------------|
| Recall@1 | {comp_dbsf["improvements"]["recall@1"]["relative_improvement_pct"]:+.1f}% |
| Recall@10 | {comp_dbsf["improvements"]["recall@10"]["relative_improvement_pct"]:+.1f}% |
| NDCG@10 | {comp_dbsf["improvements"]["ndcg@10"]["relative_improvement_pct"]:+.1f}% |
| MRR | {comp_dbsf["improvements"]["mrr"]["relative_improvement_pct"]:+.1f}% |

### Hybrid vs DBSF+ColBERT

| Metric | Improvement |
|--------|-------------|
| Recall@1 | {comp_hybrid_dbsf["improvements"]["recall@1"]["relative_improvement_pct"]:+.1f}% |
| Recall@10 | {comp_hybrid_dbsf["improvements"]["recall@10"]["relative_improvement_pct"]:+.1f}% |
| NDCG@10 | {comp_hybrid_dbsf["improvements"]["ndcg@10"]["relative_improvement_pct"]:+.1f}% |
| MRR | {comp_hybrid_dbsf["improvements"]["mrr"]["relative_improvement_pct"]:+.1f}% |

---

## Conclusion

"""

    # Determine overall winner
    dbsf_vs_baseline = comp_dbsf["improvements"]["recall@10"]["relative_improvement_pct"]
    dbsf_vs_hybrid = comp_hybrid_dbsf["improvements"]["recall@10"]["relative_improvement_pct"]

    if dbsf_vs_baseline > 10 and dbsf_vs_hybrid > 5:
        conclusion = "✅ **DBSF+ColBERT SIGNIFICANTLY OUTPERFORMS BOTH BASELINE AND HYBRID**"
    elif dbsf_vs_baseline > 5:
        conclusion = "✅ **DBSF+ColBERT MODERATELY OUTPERFORMS BASELINE**"
    elif dbsf_vs_baseline > 0:
        conclusion = "⚠️ **DBSF+ColBERT SLIGHTLY OUTPERFORMS BASELINE**"
    else:
        conclusion = "❌ **BASELINE STILL PERFORMS BEST - INVESTIGATE DBSF+ColBERT IMPLEMENTATION**"

    md += f"{conclusion}\n\n"
    md += f"**Recommendation:** {'Use DBSF+ColBERT for production' if dbsf_vs_baseline > 5 else 'Continue using Baseline, investigate issues'}\n"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(md)


if __name__ == "__main__":
    import os

    # Ensure reports directory exists
    os.makedirs("reports", exist_ok=True)

    # Run A/B test
    results = run_ab_test(
        queries_file="data/queries_testset.json",
        ground_truth_file="data/ground_truth_articles.json",
        collection_name="ukraine_criminal_code_zai_full",
        output_dir="reports",
    )

    print("\n✅ All reports generated successfully!")
    print("\n📄 Reports saved to: reports/")
