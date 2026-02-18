#!/usr/bin/env python3
"""
RAGAS integration for RAG quality evaluation with Langfuse tracing.

Evaluates RAG pipeline quality using RAGAS metrics:
- Faithfulness: Claims in answer are grounded in context
- Context Precision: Retrieved chunks are relevant
- Context Recall: Ground truth is in retrieved context
- Answer Relevancy: Answer addresses the query

Thresholds:
- Faithfulness >= 0.80 (required)
- Context Precision >= 0.80
- Context Recall >= 0.90
- Answer Relevancy >= 0.80

Usage:
    # Run evaluation
    make eval-rag

    # Quick evaluation (10 samples)
    make eval-rag-quick

    # As module
    python -m src.evaluation.ragas_evaluation
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI
from ragas import evaluate
from ragas.llms import llm_factory

# RAGAS v0.4+ API - use ragas.metrics.collections instead of deprecated ragas.metrics
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from datasets import Dataset
from src.evaluation.mlflow_integration import MLflowRAGLogger


# Expose metric factories for testing (patched in unit tests)
faithfulness = Faithfulness
context_precision = ContextPrecision
context_recall = ContextRecall
answer_relevancy = AnswerRelevancy


def _maybe_build_metric(metric_factory, llm):
    """Build metric instance unless it's already a mocked object."""
    if getattr(metric_factory, "_is_mock_object", False):
        return metric_factory
    return metric_factory(llm=llm)


# Default LiteLLM configuration
DEFAULT_LITELLM_BASE_URL = "http://localhost:4000"
DEFAULT_EVAL_MODEL = "cerebras/llama-3.3-70b"  # Fast, accurate model for evaluation


# Faithfulness threshold (required >= 0.80)
FAITHFULNESS_THRESHOLD = 0.80
CONTEXT_PRECISION_THRESHOLD = 0.80
CONTEXT_RECALL_THRESHOLD = 0.90
ANSWER_RELEVANCY_THRESHOLD = 0.80
MAX_EVAL_SAMPLES = 50


def _get_evaluator_llm():
    """
    Get LLM for RAGAS evaluation via LiteLLM proxy.

    Uses LITELLM_BASE_URL env var or defaults to localhost:4000.
    Uses EVAL_MODEL env var or defaults to cerebras/llama-3.3-70b.
    """
    base_url = os.getenv("LITELLM_BASE_URL", DEFAULT_LITELLM_BASE_URL)
    model = os.getenv("EVAL_MODEL", DEFAULT_EVAL_MODEL)

    try:
        client = OpenAI(
            api_key="not-needed",  # LiteLLM handles auth
            base_url=base_url,
        )
        # Use litellm adapter for compatibility with any model
        llm = llm_factory(model, client=client, adapter="litellm")
        print(f"   RAGAS evaluator LLM: {model} via {base_url}")
        return llm
    except Exception as e:
        print(f"   Failed to create evaluator LLM: {e}")
        raise


def _get_langfuse_client():
    """Get Langfuse client if available and enabled."""
    if os.getenv("LANGFUSE_TRACING_ENABLED", "").lower() not in ("true", "1", "yes"):
        return None

    try:
        from langfuse import Langfuse

        return Langfuse(
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        )
    except Exception as e:
        print(f"   Langfuse not available: {e}")
        return None


def _log_ragas_scores_to_langfuse(
    langfuse_client: Any,
    metrics: dict[str, float],
    session_id: str,
    trace_name: str = "ragas-evaluation",
) -> str | None:
    """
    Log RAGAS evaluation scores to Langfuse.

    Args:
        langfuse_client: Langfuse client instance
        metrics: Dictionary of RAGAS metrics
        session_id: Session ID for grouping traces
        trace_name: Name for the trace

    Returns:
        Trace ID if successful, None otherwise
    """
    if langfuse_client is None:
        return None

    try:
        # Create trace for this evaluation
        trace = langfuse_client.trace(
            name=trace_name,
            session_id=session_id,
            input={"evaluation_type": "ragas", "metrics_count": len(metrics)},
            tags=["ragas", "evaluation", "quality"],
            metadata={
                "thresholds": {
                    "faithfulness": FAITHFULNESS_THRESHOLD,
                    "context_precision": CONTEXT_PRECISION_THRESHOLD,
                    "context_recall": CONTEXT_RECALL_THRESHOLD,
                    "answer_relevancy": ANSWER_RELEVANCY_THRESHOLD,
                }
            },
        )

        # Log each RAGAS metric as a score
        score_names = [
            "faithfulness",
            "context_precision",
            "context_recall",
            "answer_relevancy",
        ]

        for score_name in score_names:
            if score_name in metrics:
                trace.score(
                    name=score_name,
                    value=metrics[score_name],
                    comment=f"RAGAS {score_name} score",
                )

        # Log additional metrics
        if "eval_duration_seconds" in metrics:
            trace.score(
                name="eval_duration_seconds",
                value=metrics["eval_duration_seconds"],
                comment="Evaluation duration in seconds",
            )

        if "queries_evaluated" in metrics:
            trace.score(
                name="queries_evaluated",
                value=float(metrics["queries_evaluated"]),
                comment="Number of queries evaluated",
            )

        # Log pass/fail status
        passed = metrics.get("faithfulness", 0) >= FAITHFULNESS_THRESHOLD
        trace.score(
            name="acceptance_passed",
            value=1.0 if passed else 0.0,
            comment=f"Faithfulness threshold {FAITHFULNESS_THRESHOLD} {'met' if passed else 'not met'}",
        )

        # Update trace output
        trace.update(
            output={
                "metrics": metrics,
                "acceptance_passed": passed,
            }
        )

        # Flush to ensure scores are sent
        langfuse_client.flush()

        return trace.id

    except Exception as e:
        print(f"   Langfuse scoring failed: {e}")
        return None


class RAGASEvaluator:
    """Evaluate RAG quality with RAGAS metrics and Langfuse integration."""

    def __init__(self, experiment_name: str = "ragas_quality_baseline"):
        """
        Initialize RAGAS evaluator with MLflow and Langfuse tracking.

        Args:
            experiment_name: MLflow experiment name
        """
        self.mlflow_logger = MLflowRAGLogger(experiment_name=experiment_name)
        self.langfuse_client = _get_langfuse_client()

        # Get evaluator LLM via LiteLLM
        evaluator_llm = _get_evaluator_llm()

        # RAGAS v0.4+ metrics - instantiate with LLM
        self.metrics = [
            _maybe_build_metric(faithfulness, evaluator_llm),  # Claims in answer are grounded
            _maybe_build_metric(context_precision, evaluator_llm),  # Retrieved chunks are relevant
            _maybe_build_metric(context_recall, evaluator_llm),  # Ground truth is in context
            _maybe_build_metric(answer_relevancy, evaluator_llm),  # Answer addresses the query
        ]

        # Thresholds
        self.faithfulness_threshold = FAITHFULNESS_THRESHOLD

    async def evaluate_pipeline(
        self,
        rag_pipeline,
        test_set_path: str = "tests/eval/ground_truth.json",
        sample_size: int | None = None,
    ) -> dict[str, float]:
        """
        Evaluate RAG pipeline with RAGAS metrics.

        Args:
            rag_pipeline: RAG pipeline to evaluate
            test_set_path: Path to evaluation dataset
            sample_size: Number of samples to evaluate (None = all)

        Returns:
            Dictionary with RAGAS evaluation results
        """
        # Load evaluation dataset
        dataset_path = Path(test_set_path)
        if not dataset_path.is_absolute():
            dataset_path = Path(__file__).parent.parent.parent / test_set_path

        with open(dataset_path, encoding="utf-8") as f:
            test_set = json.load(f)

        samples = test_set.get("samples", test_set.get("queries", []))

        # Apply sample size limit
        if sample_size:
            samples = samples[:sample_size]
        elif len(samples) > MAX_EVAL_SAMPLES:
            samples = samples[:MAX_EVAL_SAMPLES]

        print(f"   Evaluating {len(samples)} samples from {dataset_path.name}...")

        # Run RAG pipeline on all samples
        results = []
        for sample in samples:
            question = sample.get("question", sample.get("query", ""))

            # Get RAG response
            try:
                response = await rag_pipeline.query(question, top_k=10)
            except Exception as e:
                print(f"   Failed query '{question[:50]}...': {e}")
                continue

            # Format for RAGAS
            results.append(
                {
                    "question": question,
                    "answer": response.get("answer", ""),
                    "contexts": [r.get("text", "") for r in response.get("results", [])[:5]],
                    "ground_truth": sample.get("ground_truth", sample.get("expected_answer", "")),
                }
            )

        if not results:
            print("   No valid results to evaluate")
            return {}

        # Convert to RAGAS dataset format
        dataset = Dataset.from_list(results)

        # Run RAGAS evaluation
        print("   Running RAGAS evaluation...")
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
            "queries_evaluated": len(results),
        }

        # Print results
        self._print_results(metrics)

        # Log to Langfuse
        session_id = f"ragas-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        trace_id = _log_ragas_scores_to_langfuse(self.langfuse_client, metrics, session_id)
        if trace_id:
            print(f"   Langfuse trace: {trace_id}")

        # Log to MLflow
        run_name = f"ragas_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with self.mlflow_logger.start_run(
            run_name=run_name,
            tags={"evaluation_type": "ragas", "dataset": dataset_path.name},
        ):
            self.mlflow_logger.log_metrics(metrics)
            self.mlflow_logger.log_dict_artifact(
                {"results": results, "metrics": metrics},
                "ragas_evaluation.json",
                artifact_path="ragas",
            )
            print(f"   MLflow run: {self.mlflow_logger.get_run_url()}")

        # Check acceptance criteria
        self._check_acceptance(metrics)

        return metrics

    def _print_results(self, metrics: dict[str, float]) -> None:
        """Print RAGAS results to console."""
        print("\n   RAGAS Results:")
        print(
            f"   Faithfulness:       {metrics['faithfulness']:.3f} (threshold: >= {FAITHFULNESS_THRESHOLD})"
        )
        print(
            f"   Context Precision:  {metrics['context_precision']:.3f} (threshold: >= {CONTEXT_PRECISION_THRESHOLD})"
        )
        print(
            f"   Context Recall:     {metrics['context_recall']:.3f} (threshold: >= {CONTEXT_RECALL_THRESHOLD})"
        )
        print(
            f"   Answer Relevancy:   {metrics['answer_relevancy']:.3f} (threshold: >= {ANSWER_RELEVANCY_THRESHOLD})"
        )
        print(f"   Duration:           {metrics['eval_duration_seconds']:.1f}s")
        print(f"   Samples:            {int(metrics['queries_evaluated'])}")

    def _check_acceptance(self, metrics: dict[str, float]) -> bool:
        """Check if metrics meet acceptance criteria."""
        passed = metrics["faithfulness"] >= self.faithfulness_threshold

        if passed:
            print("\n   ACCEPTANCE: PASSED (faithfulness >= 0.80)")
        else:
            print(f"\n   ACCEPTANCE: FAILED (faithfulness {metrics['faithfulness']:.3f} < 0.80)")
            print("   Action required: Improve retrieval quality or LLM grounding")

        return passed


def evaluate_with_mock_pipeline(
    test_set_path: str = "tests/eval/ground_truth.json",
    sample_size: int | None = None,
) -> dict[str, float]:
    """
    Run evaluation with a mock pipeline for testing.

    Args:
        test_set_path: Path to evaluation dataset
        sample_size: Number of samples to evaluate

    Returns:
        RAGAS evaluation metrics
    """

    class MockRAGPipeline:
        """Mock pipeline that returns ground truth as answer."""

        async def query(self, question: str, top_k: int = 10) -> dict:
            return {
                "answer": f"Mock answer for: {question[:50]}",
                "results": [{"text": f"Context chunk for {question[:30]}"}],
            }

    async def _run():
        evaluator = RAGASEvaluator()
        pipeline = MockRAGPipeline()
        return await evaluator.evaluate_pipeline(
            pipeline, test_set_path=test_set_path, sample_size=sample_size
        )

    return asyncio.run(_run())


async def run_ragas_evaluation():
    """Run RAGAS evaluation with the production RAG pipeline."""
    try:
        from src.core.pipeline import RAGPipeline
    except ImportError:
        print("   RAGPipeline not available, using mock pipeline")
        sample_size = int(os.getenv("EVAL_SAMPLE_SIZE", "0")) or None
        return evaluate_with_mock_pipeline(sample_size=sample_size)

    evaluator = RAGASEvaluator()
    pipeline = RAGPipeline()

    sample_size = int(os.getenv("EVAL_SAMPLE_SIZE", "0")) or None
    metrics = await evaluator.evaluate_pipeline(pipeline, sample_size=sample_size)

    # Alert if faithfulness drops below threshold
    if metrics.get("faithfulness", 0) < FAITHFULNESS_THRESHOLD:
        print(f"   ALERT: Faithfulness {metrics['faithfulness']:.3f} < {FAITHFULNESS_THRESHOLD}")

    return metrics


if __name__ == "__main__":
    print("=" * 60)
    print("RAG Evaluation with RAGAS")
    print("=" * 60)

    try:
        metrics = asyncio.run(run_ragas_evaluation())
        print("\n" + "=" * 60)

        # Exit with error if acceptance criteria not met
        if metrics.get("faithfulness", 0) < FAITHFULNESS_THRESHOLD:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n   Evaluation cancelled")
        sys.exit(130)
    except Exception as e:
        print(f"\n   Evaluation failed: {e}")
        sys.exit(1)
