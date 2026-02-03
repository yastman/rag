#!/usr/bin/env python3
"""
RAGAS Evaluation for Contextual RAG

End-to-end RAG evaluation using RAGAS framework with MLflow tracking.

Features:
    - Faithfulness: LLM answers without hallucinations
    - Context Relevance: Retrieved documents are relevant
    - Answer Relevancy: Answer addresses the question
    - Context Recall: Ground truth in retrieved context

Metrics (from RAGAS 0.2+):
    - faithfulness: [0, 1] - Higher = less hallucination
    - context_relevancy: [0, 1] - Higher = better retrieval
    - answer_relevancy: [0, 1] - Higher = more relevant answer
    - context_recall: [0, 1] - Higher = better ground truth coverage

Usage:
    python evaluate_with_ragas.py --engine dbsf_colbert --sample 10
    python evaluate_with_ragas.py --engine baseline --use-mlflow

Integration:
    - Uses search_engines.py for retrieval
    - Logs to MLflow (optional)
    - Uses OpenAI API for RAGAS evaluation (gpt-4o-mini)
    - Exports results to JSON

Environment variables:
    OPENAI_API_KEY: OpenAI API key for RAGAS evaluation
    MLFLOW_TRACKING_URI: MLflow server URL (default: http://localhost:5000)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Load environment variables first
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import search engines and MLflow integration (after load_dotenv)
from mlflow_integration import MLflowRAGLogger
from search_engines import (
    BaselineSearchEngine,
    HybridDBSFColBERTSearchEngine,
    HybridSearchEngine,
)


def evaluate_with_ragas(
    engine_name: str = "dbsf_colbert",
    collection: str = "uk_civil_code_v2",
    queries_file: str = "data/queries_testset.json",
    sample: int | None = None,
    use_mlflow: bool = False,
    output_file: str | None = None,
) -> dict[str, Any]:
    """
    Run RAGAS evaluation on search engine.

    Args:
        engine_name: Search engine to evaluate (baseline, hybrid, dbsf_colbert)
        collection: Qdrant collection name
        queries_file: Path to queries JSON file
        sample: Number of queries to sample (None = all)
        use_mlflow: Log results to MLflow
        output_file: Path to save results JSON

    Returns:
        Dictionary with evaluation results
    """
    print("=" * 80)
    print("🎯 RAGAS EVALUATION - End-to-End RAG Quality")
    print("=" * 80)

    # Check for RAGAS and datasets
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_recall,
            context_relevancy,
            faithfulness,
        )
    except ImportError as e:
        print("\n❌ Error: RAGAS not installed")
        print(f"   {e}")
        print("\n💡 Install with: pip install ragas datasets")
        sys.exit(1)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ Error: OPENAI_API_KEY not set in environment")
        print("   RAGAS requires OpenAI API for evaluation")
        sys.exit(1)

    print("\n📋 Configuration:")
    print(f"   Engine: {engine_name}")
    print(f"   Collection: {collection}")
    print(f"   Queries File: {queries_file}")
    print(f"   Sample: {sample if sample else 'all'}")
    print(f"   MLflow: {'enabled' if use_mlflow else 'disabled'}")

    # Initialize search engine
    print(f"\n🔧 Initializing {engine_name} engine...")
    if engine_name == "baseline":
        engine = BaselineSearchEngine(collection_name=collection)
    elif engine_name == "hybrid":
        engine = HybridSearchEngine(collection_name=collection)
    elif engine_name == "dbsf_colbert":
        engine = HybridDBSFColBERTSearchEngine(collection_name=collection)
    else:
        raise ValueError(f"Unknown engine: {engine_name}")

    # Load queries
    print(f"\n📚 Loading queries from {queries_file}...")
    queries_path = Path(__file__).parent / queries_file
    with open(queries_path) as f:
        queries_data = json.load(f)

    if sample:
        queries_data = queries_data[:sample]

    print(f"   Loaded {len(queries_data)} queries")

    # Initialize MLflow logger if requested
    mlflow_logger = None
    if use_mlflow:
        print("\n📊 Initializing MLflow logger...")
        mlflow_logger = MLflowRAGLogger(experiment_name="ragas_evaluation")
        print(f"   MLflow UI: {mlflow_logger.tracking_uri}")

    # Prepare RAGAS dataset
    print("\n🏃 Running RAGAS evaluation...")
    ragas_data: dict = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    for i, query_item in enumerate(queries_data, 1):
        query = query_item["query"]
        expected_article = query_item.get("expected_article")

        print(f"   [{i}/{len(queries_data)}] Processing: {query[:60]}...")

        # Search for documents
        try:
            results = engine.search(query, limit=10)

            # Extract contexts (retrieved document texts)
            contexts = []
            for result in results[:5]:  # Use top 5 for context
                text = result.text  # SearchResult.text already contains page_content
                contexts.append(text)

            # Generate answer using LLM (simplified - just use first doc)
            # In production, you'd use your full RAG pipeline here
            answer = contexts[0] if contexts else "No answer found"

            # Ground truth (expected article text)
            ground_truth = f"Article {expected_article}" if expected_article else ""

            # Add to RAGAS dataset
            ragas_data["question"].append(query)
            ragas_data["answer"].append(answer)
            ragas_data["contexts"].append(contexts)
            ragas_data["ground_truth"].append(ground_truth)

        except Exception as e:
            print(f"      ⚠️  Error processing query: {e}")
            continue

    # Convert to RAGAS dataset
    print("\n🔄 Creating RAGAS dataset...")
    dataset = Dataset.from_dict(ragas_data)
    print(f"   Dataset size: {len(dataset)} queries")

    # Run RAGAS evaluation
    print("\n🎯 Evaluating with RAGAS metrics...")
    print("   This may take a few minutes (using OpenAI API)...")

    try:
        result = evaluate(
            dataset,
            metrics=[
                faithfulness,
                context_relevancy,
                answer_relevancy,
                context_recall,
            ],
        )

        print("\n✅ RAGAS evaluation complete!")

    except Exception as e:
        print(f"\n❌ RAGAS evaluation failed: {e}")
        sys.exit(1)

    # Extract metrics
    metrics = {
        "faithfulness": float(result["faithfulness"]),
        "context_relevancy": float(result["context_relevancy"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "context_recall": float(result["context_recall"]),
        "ragas_score": float(
            sum(
                [
                    result["faithfulness"],
                    result["context_relevancy"],
                    result["answer_relevancy"],
                    result["context_recall"],
                ]
            )
            / 4
        ),
    }

    # Print results
    print("\n" + "=" * 80)
    print("📊 RAGAS EVALUATION RESULTS")
    print("=" * 80)
    print(f"\n🎯 Overall RAGAS Score: {metrics['ragas_score']:.3f}")
    print("\n📈 Detailed Metrics:")
    print(f"   Faithfulness:       {metrics['faithfulness']:.3f} (less hallucination)")
    print(f"   Context Relevancy:  {metrics['context_relevancy']:.3f} (better retrieval)")
    print(f"   Answer Relevancy:   {metrics['answer_relevancy']:.3f} (relevant answers)")
    print(f"   Context Recall:     {metrics['context_recall']:.3f} (ground truth coverage)")
    print("\n" + "=" * 80)

    # Log to MLflow
    if mlflow_logger:
        print("\n📊 Logging to MLflow...")
        run_name = f"ragas_{engine_name}_{time.strftime('%Y%m%d_%H%M%S')}"

        with mlflow_logger.start_run(run_name=run_name, tags={"engine": engine_name}):
            # Log config
            config = {
                "engine": engine_name,
                "collection": collection,
                "num_queries": len(queries_data),
                "ragas_metrics": [
                    "faithfulness",
                    "context_relevancy",
                    "answer_relevancy",
                    "context_recall",
                ],
            }
            mlflow_logger.log_config(config)

            # Log metrics
            mlflow_logger.log_metrics(metrics)

            # Log dataset as artifact
            mlflow_logger.log_dict_artifact(ragas_data, "ragas_dataset.json", artifact_path="data")

            run_url = mlflow_logger.get_run_url()
            print(f"   MLflow Run: {run_url}")

    # Save results to file
    if output_file:
        output_path = Path(__file__).parent / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        results_data = {
            "engine": engine_name,
            "collection": collection,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "num_queries": len(queries_data),
            "metrics": metrics,
            "ragas_data": ragas_data,
        }

        with open(output_path, "w") as f:
            json.dump(results_data, f, indent=2)

        print(f"\n💾 Results saved to: {output_path}")

    return {
        "engine": engine_name,
        "metrics": metrics,
        "num_queries": len(queries_data),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG system with RAGAS framework")
    parser.add_argument(
        "--engine",
        choices=["baseline", "hybrid", "dbsf_colbert"],
        default="dbsf_colbert",
        help="Search engine to evaluate",
    )
    parser.add_argument(
        "--collection",
        default="uk_civil_code_v2",
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--queries",
        default="data/queries_testset.json",
        help="Path to queries JSON file",
    )
    parser.add_argument(
        "--sample",
        type=int,
        help="Number of queries to sample (default: all)",
    )
    parser.add_argument(
        "--use-mlflow",
        action="store_true",
        help="Log results to MLflow",
    )
    parser.add_argument(
        "--output",
        help="Path to save results JSON",
    )

    args = parser.parse_args()

    result = evaluate_with_ragas(
        engine_name=args.engine,
        collection=args.collection,
        queries_file=args.queries,
        sample=args.sample,
        use_mlflow=args.use_mlflow,
        output_file=args.output,
    )

    sys.exit(0)
