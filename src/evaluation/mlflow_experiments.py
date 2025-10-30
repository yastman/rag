#!/usr/bin/env python3
"""
MLflow-powered A/B Testing Framework for RAG Pipeline

Best Practice 2025:
- Structured experiments with automatic comparison
- Config versioning and reproducibility
- Side-by-side metric comparison
- Artifact storage for deep analysis

Usage:
    runner = RAGExperimentRunner(experiment_name="contextual_rag_ab_tests")

    # Test 1: Context vs No Context
    await runner.run_ab_test(
        test_name="context_vs_no_context",
        variant_a={"enable_contextualization": True},
        variant_b={"enable_contextualization": False},
        test_queries=test_queries
    )
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.evaluation.mlflow_integration import MLflowRAGLogger


class RAGExperimentRunner:
    """
    Run structured A/B experiments with MLflow tracking.

    Enables systematic comparison of:
    - Chunking strategies (size, overlap)
    - Contextualization (enabled vs disabled)
    - Search engines (baseline, hybrid, dbsf_colbert)
    - Embedding models (bge-m3, bge-m3-mini)
    """

    def __init__(self, experiment_name: str = "contextual_rag_ab_tests"):
        """
        Initialize experiment runner.

        Args:
            experiment_name: MLflow experiment name for grouping tests
        """
        self.experiment_name = experiment_name
        self.logger = MLflowRAGLogger(experiment_name=experiment_name)

        print("📊 Experiment Runner initialized")
        print(f"   Experiment: {experiment_name}")
        print(f"   MLflow UI: {self.logger.tracking_uri}")

    async def run_ab_test(
        self,
        test_name: str,
        variant_a: dict[str, Any],
        variant_b: dict[str, Any],
        test_queries: list[dict[str, Any]],
        variant_a_name: str = "A",
        variant_b_name: str = "B",
    ) -> dict[str, Any]:
        """
        Run A/B test between two variants.

        Args:
            test_name: Test identifier (e.g., "context_vs_no_context")
            variant_a: Config for variant A
            variant_b: Config for variant B
            test_queries: List of test queries with ground truth
            variant_a_name: Display name for variant A
            variant_b_name: Display name for variant B

        Returns:
            Comparison results with winner

        Example:
            results = await runner.run_ab_test(
                test_name="chunk_size_comparison",
                variant_a={"chunk_size": 400, "overlap": 100},
                variant_b={"chunk_size": 800, "overlap": 200},
                test_queries=[
                    {"query": "Стаття 121 УК", "expected_article": 121},
                    {"query": "Конституція України", "expected_article": 1},
                ]
            )
        """
        print("\n" + "=" * 80)
        print(f"🧪 A/B TEST: {test_name}")
        print("=" * 80)
        print(f"\n{variant_a_name}: {variant_a}")
        print(f"{variant_b_name}: {variant_b}")
        print(f"\nTest queries: {len(test_queries)}")
        print("=" * 80)

        # Run Variant A
        print(f"\n🔬 Running Variant {variant_a_name}...")
        results_a = await self._run_variant(
            test_name=test_name,
            variant_name=variant_a_name,
            variant_config=variant_a,
            test_queries=test_queries,
        )

        # Run Variant B
        print(f"\n🔬 Running Variant {variant_b_name}...")
        results_b = await self._run_variant(
            test_name=test_name,
            variant_name=variant_b_name,
            variant_config=variant_b,
            test_queries=test_queries,
        )

        # Compare
        comparison = self._compare_variants(
            test_name=test_name,
            variant_a_name=variant_a_name,
            variant_b_name=variant_b_name,
            results_a=results_a,
            results_b=results_b,
        )

        print("\n" + "=" * 80)
        print("📊 A/B TEST RESULTS")
        print("=" * 80)
        print(
            f"\n{variant_a_name}: Recall@1={results_a['recall_at_1']:.3f}, "
            f"NDCG@10={results_a['ndcg_at_10']:.3f}, "
            f"Latency={results_a['latency_p95_ms']:.0f}ms"
        )
        print(
            f"{variant_b_name}: Recall@1={results_b['recall_at_1']:.3f}, "
            f"NDCG@10={results_b['ndcg_at_10']:.3f}, "
            f"Latency={results_b['latency_p95_ms']:.0f}ms"
        )
        print(f"\n🏆 Winner: Variant {comparison['winner']} ({comparison['reason']})")
        print("=" * 80)

        return comparison

    async def _run_variant(
        self,
        test_name: str,
        variant_name: str,
        variant_config: dict[str, Any],
        test_queries: list[dict[str, Any]],
    ) -> dict[str, float]:
        """
        Run single variant evaluation.

        Args:
            test_name: Test identifier
            variant_name: Variant identifier (A or B)
            variant_config: Variant configuration
            test_queries: Test queries

        Returns:
            Evaluation metrics
        """
        run_name = f"{test_name}_{variant_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with self.logger.start_run(
            run_name=run_name,
            tags={
                "test": test_name,
                "variant": variant_name,
                "test_type": "ab_test",
            },
        ):
            # Log variant config
            self.logger.log_config(variant_config, prefix=f"variant_{variant_name}.")

            # Simulate evaluation (replace with actual evaluation logic)
            # TODO: Integrate with actual RAG pipeline
            results = await self._simulate_evaluation(variant_config, test_queries)

            # Log metrics
            self.logger.log_metrics(results)

            return results

    async def _simulate_evaluation(
        self, config: dict[str, Any], test_queries: list[dict[str, Any]]
    ) -> dict[str, float]:
        """
        Simulate evaluation (placeholder for actual evaluation).

        In production, this would:
        1. Initialize RAG pipeline with config
        2. Run test queries
        3. Calculate metrics (recall, ndcg, latency)
        4. Return results

        Args:
            config: Variant configuration
            test_queries: Test queries

        Returns:
            Simulated metrics
        """
        # Simulate processing time
        await asyncio.sleep(0.1 * len(test_queries))

        # Simulate metrics (placeholder)
        # TODO: Replace with actual evaluation
        base_recall = 0.90
        base_ndcg = 0.95
        base_latency = 400

        # Adjust based on config
        if config.get("enable_contextualization"):
            base_recall += 0.04  # Context improves recall
            base_latency += 50  # But adds latency

        if config.get("chunk_size", 600) < 500:
            base_recall -= 0.02  # Smaller chunks hurt recall

        return {
            "recall_at_1": base_recall,
            "recall_at_10": base_recall + 0.05,
            "precision_at_1": base_recall,
            "ndcg_at_10": base_ndcg,
            "mrr": base_recall + 0.03,
            "latency_p50_ms": base_latency * 0.8,
            "latency_p95_ms": base_latency,
            "latency_p99_ms": base_latency * 1.2,
        }

    def _compare_variants(
        self,
        test_name: str,
        variant_a_name: str,
        variant_b_name: str,
        results_a: dict[str, float],
        results_b: dict[str, float],
    ) -> dict[str, Any]:
        """
        Compare two variants and determine winner.

        Args:
            test_name: Test identifier
            variant_a_name: Variant A name
            variant_b_name: Variant B name
            results_a: Variant A metrics
            results_b: Variant B metrics

        Returns:
            Comparison results
        """
        # Primary metric: Recall@1
        recall_diff = results_a["recall_at_1"] - results_b["recall_at_1"]

        if abs(recall_diff) < 0.01:  # Statistical tie
            # Secondary: Latency (lower is better)
            if results_a["latency_p95_ms"] < results_b["latency_p95_ms"]:
                winner = variant_a_name
                reason = "Similar recall, better latency"
            else:
                winner = variant_b_name
                reason = "Similar recall, better latency"
        elif recall_diff > 0:
            winner = variant_a_name
            reason = f"Higher Recall@1 (+{recall_diff:.1%})"
        else:
            winner = variant_b_name
            reason = f"Higher Recall@1 (+{-recall_diff:.1%})"

        return {
            "test_name": test_name,
            "winner": winner,
            "reason": reason,
            "variant_a": {"name": variant_a_name, "metrics": results_a},
            "variant_b": {"name": variant_b_name, "metrics": results_b},
            "delta": {
                "recall_at_1": recall_diff,
                "ndcg_at_10": results_a["ndcg_at_10"] - results_b["ndcg_at_10"],
                "latency_p95_ms": results_a["latency_p95_ms"] - results_b["latency_p95_ms"],
            },
        }


async def main():
    """Example usage of A/B testing framework."""
    print("=" * 80)
    print("🧪 RAG A/B TESTING FRAMEWORK - Example")
    print("=" * 80)

    runner = RAGExperimentRunner(experiment_name="contextual_rag_ab_tests_example")

    # Example test queries (replace with real queries)
    test_queries = [
        {"query": "Стаття 121 УК", "expected_article": 121},
        {"query": "Конституція України", "expected_article": 1},
        {"query": "Громадянський кодекс", "expected_article": 1},
    ]

    # Test 1: Context vs No Context
    print("\n\n📝 Test 1: Context vs No Context")
    await runner.run_ab_test(
        test_name="context_vs_no_context",
        variant_a={"enable_contextualization": True},
        variant_b={"enable_contextualization": False},
        test_queries=test_queries,
        variant_a_name="With Context",
        variant_b_name="No Context",
    )

    # Test 2: Chunk Size Comparison
    print("\n\n📝 Test 2: Chunk Size (400 vs 800)")
    await runner.run_ab_test(
        test_name="chunk_size_400_vs_800",
        variant_a={"chunk_size": 400, "overlap": 100},
        variant_b={"chunk_size": 800, "overlap": 200},
        test_queries=test_queries,
        variant_a_name="Small Chunks (400)",
        variant_b_name="Large Chunks (800)",
    )

    print("\n" + "=" * 80)
    print("✅ A/B Testing Complete!")
    print("📊 View results: http://localhost:5000")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
