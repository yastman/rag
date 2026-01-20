#!/usr/bin/env python3
"""
A/B Evaluation: Baseline vs Contextual+KG
Compares retrieval quality metrics
"""

import json
import sys
from datetime import datetime

import requests

from config import (
    BGE_M3_TIMEOUT,
    BGE_M3_URL,
    COLLECTION_BASELINE,
    COLLECTION_CONTEXTUAL_KG,
    EVALUATION_QUERIES_FILE,
    EVALUATION_RESULTS_FILE,
    QDRANT_API_KEY,
    QDRANT_URL,
    validate_config,
)


def print_header(text: str):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def print_step(num: int, text: str):
    print(f"\n{'─' * 80}")
    print(f"STEP {num}: {text}")
    print("─" * 80)


def bge_m3_encode(text: str) -> dict:
    """Encode query with BGE-M3."""
    response = requests.post(
        f"{BGE_M3_URL}/encode/hybrid", json={"texts": [text]}, timeout=BGE_M3_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def qdrant_search(collection: str, query_vector: dict, limit: int = 10) -> dict:
    """Search Qdrant with dense vectors only (for simplicity)."""
    data = {
        "vector": {"name": "dense", "vector": query_vector["dense_vecs"][0]},
        "limit": limit,
        "with_payload": True,
    }

    response = requests.post(
        f"{QDRANT_URL}/collections/{collection}/points/search",
        json=data,
        headers={"api-key": QDRANT_API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def calculate_recall_at_k(results: list[dict], relevant_ids: list[int], k: int) -> float:
    """Calculate Recall@K."""
    if not relevant_ids:
        return 0.0

    top_k = results[:k]
    retrieved_ids = {r["id"] for r in top_k}
    relevant_retrieved = len(retrieved_ids.intersection(relevant_ids))

    return relevant_retrieved / len(relevant_ids)


def calculate_ndcg_at_k(results: list[dict], relevant_ids: list[int], k: int) -> float:
    """Calculate NDCG@K."""
    if not relevant_ids:
        return 0.0

    # DCG
    dcg = 0.0
    for i, result in enumerate(results[:k]):
        if result["id"] in relevant_ids:
            # 1-based position
            dcg += 1.0 / (i + 1)

    # IDCG (ideal DCG)
    idcg = sum(1.0 / (i + 1) for i in range(min(k, len(relevant_ids))))

    if idcg == 0:
        return 0.0

    return dcg / idcg


def is_failure(results: list[dict], relevant_ids: list[int], k: int) -> bool:
    """Check if query failed (no relevant docs in top-K)."""
    if not relevant_ids:
        return False

    top_k = results[:k]
    retrieved_ids = {r["id"] for r in top_k}

    return len(retrieved_ids.intersection(relevant_ids)) == 0


def evaluate_collections(
    baseline_collection: str,
    contextual_collection: str,
    queries_file: str,
    k_values: list[int] | None = None,
):
    """
    Evaluate both collections and compare.

    Args:
        baseline_collection: Name of baseline collection
        contextual_collection: Name of contextual+KG collection
        queries_file: Path to evaluation queries JSON
        k_values: List of K values for metrics
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]
    print_header("🔬 A/B EVALUATION: BASELINE vs CONTEXTUAL+KG")

    # Load queries
    print_step(1, "LOADING EVALUATION QUERIES")
    with open(queries_file, encoding="utf-8") as f:
        data = json.load(f)
        queries = data["queries"]

    print(f"  ✓ Loaded {len(queries)} evaluation queries")

    # Initialize metrics storage
    metrics = {
        "baseline": {
            "recall": {k: [] for k in k_values},
            "ndcg": {k: [] for k in k_values},
            "failures": dict.fromkeys(k_values, 0),
            "total": 0,
        },
        "contextual": {
            "recall": {k: [] for k in k_values},
            "ndcg": {k: [] for k in k_values},
            "failures": dict.fromkeys(k_values, 0),
            "total": 0,
        },
    }

    # Evaluate each query
    print_step(2, "EVALUATING QUERIES")
    print()

    for idx, query_data in enumerate(queries):
        query_text = query_data["query"]
        # Extract chunk IDs from ground_truth
        relevant_ids = {gt["chunk_id"] for gt in query_data["ground_truth"]}

        print(f"  [{idx + 1}/{len(queries)}] Query: {query_text[:60]}...")

        try:
            # Encode query
            query_vector = bge_m3_encode(query_text)

            # Search baseline
            baseline_results = qdrant_search(baseline_collection, query_vector, limit=10)
            baseline_points = baseline_results.get("result", [])

            # Search contextual
            contextual_results = qdrant_search(contextual_collection, query_vector, limit=10)
            contextual_points = contextual_results.get("result", [])

            # Calculate metrics for each K
            for k in k_values:
                # Baseline metrics
                baseline_recall = calculate_recall_at_k(baseline_points, relevant_ids, k)
                baseline_ndcg = calculate_ndcg_at_k(baseline_points, relevant_ids, k)
                baseline_failed = is_failure(baseline_points, relevant_ids, k)

                metrics["baseline"]["recall"][k].append(baseline_recall)
                metrics["baseline"]["ndcg"][k].append(baseline_ndcg)
                if baseline_failed:
                    metrics["baseline"]["failures"][k] += 1

                # Contextual metrics
                contextual_recall = calculate_recall_at_k(contextual_points, relevant_ids, k)
                contextual_ndcg = calculate_ndcg_at_k(contextual_points, relevant_ids, k)
                contextual_failed = is_failure(contextual_points, relevant_ids, k)

                metrics["contextual"]["recall"][k].append(contextual_recall)
                metrics["contextual"]["ndcg"][k].append(contextual_ndcg)
                if contextual_failed:
                    metrics["contextual"]["failures"][k] += 1

            metrics["baseline"]["total"] += 1
            metrics["contextual"]["total"] += 1

        except Exception as e:
            print(f"    ✗ Error: {e}")
            continue

    print()

    # Calculate averages and improvements
    print_step(3, "CALCULATING FINAL METRICS")

    results = {
        "timestamp": datetime.now().isoformat(),
        "baseline_collection": baseline_collection,
        "contextual_collection": contextual_collection,
        "total_queries": len(queries),
        "k_values": k_values,
        "baseline": {},
        "contextual": {},
        "improvements": {},
    }

    for k in k_values:
        # Baseline averages
        baseline_avg_recall = (
            sum(metrics["baseline"]["recall"][k]) / len(metrics["baseline"]["recall"][k])
            if metrics["baseline"]["recall"][k]
            else 0
        )
        baseline_avg_ndcg = (
            sum(metrics["baseline"]["ndcg"][k]) / len(metrics["baseline"]["ndcg"][k])
            if metrics["baseline"]["ndcg"][k]
            else 0
        )
        baseline_failure_rate = (
            metrics["baseline"]["failures"][k] / metrics["baseline"]["total"]
            if metrics["baseline"]["total"] > 0
            else 0
        )

        results["baseline"][f"recall@{k}"] = baseline_avg_recall
        results["baseline"][f"ndcg@{k}"] = baseline_avg_ndcg
        results["baseline"][f"failure_rate@{k}"] = baseline_failure_rate

        # Contextual averages
        contextual_avg_recall = (
            sum(metrics["contextual"]["recall"][k]) / len(metrics["contextual"]["recall"][k])
            if metrics["contextual"]["recall"][k]
            else 0
        )
        contextual_avg_ndcg = (
            sum(metrics["contextual"]["ndcg"][k]) / len(metrics["contextual"]["ndcg"][k])
            if metrics["contextual"]["ndcg"][k]
            else 0
        )
        contextual_failure_rate = (
            metrics["contextual"]["failures"][k] / metrics["contextual"]["total"]
            if metrics["contextual"]["total"] > 0
            else 0
        )

        results["contextual"][f"recall@{k}"] = contextual_avg_recall
        results["contextual"][f"ndcg@{k}"] = contextual_avg_ndcg
        results["contextual"][f"failure_rate@{k}"] = contextual_failure_rate

        # Improvements (%)
        recall_improvement = (
            ((contextual_avg_recall - baseline_avg_recall) / baseline_avg_recall * 100)
            if baseline_avg_recall > 0
            else 0
        )
        ndcg_improvement = (
            ((contextual_avg_ndcg - baseline_avg_ndcg) / baseline_avg_ndcg * 100)
            if baseline_avg_ndcg > 0
            else 0
        )
        failure_improvement = (
            ((baseline_failure_rate - contextual_failure_rate) / baseline_failure_rate * 100)
            if baseline_failure_rate > 0
            else 0
        )

        results["improvements"][f"recall@{k}"] = recall_improvement
        results["improvements"][f"ndcg@{k}"] = ndcg_improvement
        results["improvements"][f"failure_rate@{k}"] = failure_improvement

        print(f"\n  📊 Metrics @ K={k}:")
        print("    Baseline:")
        print(f"      Recall@{k}:       {baseline_avg_recall:.4f}")
        print(f"      NDCG@{k}:         {baseline_avg_ndcg:.4f}")
        print(f"      Failure Rate:     {baseline_failure_rate:.2%}")
        print("    Contextual+KG:")
        print(f"      Recall@{k}:       {contextual_avg_recall:.4f}")
        print(f"      NDCG@{k}:         {contextual_avg_ndcg:.4f}")
        print(f"      Failure Rate:     {contextual_failure_rate:.2%}")
        print("    Improvements:")
        print(f"      Recall:           {recall_improvement:+.1f}%")
        print(f"      NDCG:             {ndcg_improvement:+.1f}%")
        print(f"      Failure Rate:     {failure_improvement:+.1f}%")

    # Save results
    print_step(4, "SAVING RESULTS")

    results_file = EVALUATION_RESULTS_FILE
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, indent=2, ensure_ascii=False, fp=f)

    print(f"  ✓ Results saved to: {results_file}")

    # Print summary
    print_header("✅ EVALUATION COMPLETED")
    print(f"  Total queries evaluated: {len(queries)}")
    print(f"  Results file: {results_file}")

    # Highlight key improvement
    k5_failure_improvement = results["improvements"]["failure_rate@5"]
    print(f"\n  🎯 KEY METRIC: Failure Rate@5 improved by {k5_failure_improvement:+.1f}%")

    if k5_failure_improvement > 40:
        print("  🎉 TARGET ACHIEVED! (>40% improvement)")

    print("=" * 80 + "\n")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A/B Evaluation")
    parser.add_argument("--baseline", default=COLLECTION_BASELINE, help="Baseline collection")
    parser.add_argument(
        "--contextual", default=COLLECTION_CONTEXTUAL_KG, help="Contextual+KG collection"
    )
    parser.add_argument("--queries", default=EVALUATION_QUERIES_FILE, help="Queries file")

    args = parser.parse_args()

    # Validate config
    if not validate_config():
        sys.exit(1)

    # Run evaluation
    try:
        results = evaluate_collections(
            baseline_collection=args.baseline,
            contextual_collection=args.contextual,
            queries_file=args.queries,
        )
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR: Evaluation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
