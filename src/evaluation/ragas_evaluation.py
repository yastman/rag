#!/usr/bin/env python3
"""RAGAS integration for RAG quality evaluation."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from src.evaluation.mlflow_integration import MLflowRAGLogger


class RAGASEvaluator:
    """Evaluate RAG quality with RAGAS metrics."""

    def __init__(self):
        """Initialize RAGAS evaluator with MLflow tracking."""
        self.mlflow_logger = MLflowRAGLogger(experiment_name="ragas_quality_baseline")

        # RAGAS metrics
        self.metrics = [
            faithfulness,  # Claims in answer are grounded in context
            context_precision,  # Retrieved chunks are relevant
            context_recall,  # Ground truth is in retrieved context
            answer_relevancy,  # Answer addresses the query
        ]

    async def evaluate_pipeline(
        self, rag_pipeline, golden_test_set_path: str = "tests/data/golden_test_set.json"
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
        test_set_path = Path(golden_test_set_path)
        if not test_set_path.is_absolute():
            test_set_path = Path(__file__).parent.parent.parent / golden_test_set_path

        with open(test_set_path, encoding="utf-8") as f:
            test_set = json.load(f)

        queries = test_set["queries"][:50]  # Start with 50 queries

        print(f"📊 Running RAGAS evaluation on {len(queries)} queries...")

        # Run RAG pipeline on all queries
        results = []
        for query_data in queries:
            query = query_data["query"]

            # Get RAG response
            try:
                response = await rag_pipeline.query(query, top_k=10)
            except Exception as e:
                print(f"⚠️  Failed query '{query}': {e}")
                continue

            # Format for RAGAS
            results.append(
                {
                    "question": query,
                    "answer": response.get("answer", ""),  # If generation enabled
                    "contexts": [r["text"] for r in response.get("results", [])[:5]],
                    "ground_truth": query_data.get("expected_answer", ""),
                }
            )

        # Convert to RAGAS dataset format
        dataset = Dataset.from_list(results)

        # Run RAGAS evaluation
        start_time = datetime.now()
        ragas_results = evaluate(dataset, metrics=self.metrics)
        eval_duration = (datetime.now() - start_time).total_seconds()

        # Extract metrics
        metrics = {
            "faithfulness": float(ragas_results["faithfulness"]),
            "context_precision": float(ragas_results["context_precision"]),
            "context_recall": float(ragas_results["context_recall"]),
            "answer_relevancy": float(ragas_results["answer_relevancy"]),
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
            run_name=run_name, tags={"evaluation_type": "ragas", "dataset": "golden_set_v1.0"}
        ):
            self.mlflow_logger.log_metrics(metrics)

            # Log detailed results
            self.mlflow_logger.log_dict_artifact(
                {"results": results, "metrics": metrics},
                "ragas_evaluation.json",
                artifact_path="ragas",
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
