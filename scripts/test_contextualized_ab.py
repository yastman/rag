#!/usr/bin/env python3
"""A/B test for Voyage Contextualized Embeddings (voyage-context-3).

Compares baseline Voyage embeddings (voyage-3-large) against contextualized
embeddings (voyage-context-3) for document retrieval quality.

Measures:
1. Latency: avg embedding + search time with/without contextualization
2. Overlap: % of same results in top-k (stability metric)
3. Precision@k: % of relevant docs in top-k (quality metric)
4. Recall@k: % of relevant docs retrieved (coverage metric)

Usage:
    python scripts/test_contextualized_ab.py
    python scripts/test_contextualized_ab.py --k 5 --runs 3
    python scripts/test_contextualized_ab.py --ground-truth tests/eval/ground_truth.json
"""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from telegram_bot.config import BotConfig
from telegram_bot.services.qdrant import QdrantService
from telegram_bot.services.voyage import VoyageService


# Optional: import contextualized service if available
try:
    from src.models.contextualized_embedding import ContextualizedEmbeddingService

    CONTEXTUALIZED_AVAILABLE = True
except ImportError:
    CONTEXTUALIZED_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def precision_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Calculate Precision@K: fraction of retrieved docs that are relevant."""
    if not relevant_ids or k == 0:
        return 0.0
    retrieved_k = set(retrieved_ids[:k])
    relevant_set = set(relevant_ids)
    return len(retrieved_k & relevant_set) / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """Calculate Recall@K: fraction of relevant docs that are retrieved."""
    if not relevant_ids:
        return 0.0
    retrieved_k = set(retrieved_ids[:k])
    relevant_set = set(relevant_ids)
    return len(retrieved_k & relevant_set) / len(relevant_set)


async def run_ab_test(
    k: int = 5,
    num_runs: int = 1,
    ground_truth_path: Path | None = None,
    output_dimension: int = 1024,
):
    """Run A/B test comparing baseline vs contextualized embeddings.

    Args:
        k: Number of top results to compare
        num_runs: Number of test iterations
        ground_truth_path: Path to ground truth JSON file
        output_dimension: Embedding dimension (1024 or 2048)
    """
    if not CONTEXTUALIZED_AVAILABLE:
        logger.error(
            "ContextualizedEmbeddingService not available. "
            "Ensure src/models/contextualized_embedding.py exists."
        )
        return False

    config = BotConfig()

    # Initialize services
    baseline_voyage = VoyageService(api_key=config.voyage_api_key)
    contextualized = ContextualizedEmbeddingService(
        api_key=config.voyage_api_key,
        output_dimension=output_dimension,
    )
    qdrant = QdrantService(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection_name=config.qdrant_collection,
    )

    # Load ground truth if available
    ground_truth: dict[str, list[str]] = {}
    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path) as f:
            gt_data = json.load(f)
            # Support both formats: list of dicts or dict of query->ids
            if isinstance(gt_data, list):
                ground_truth = {
                    item.get("query", item.get("question", "")): item.get(
                        "relevant_ids", item.get("ground_truth_ids", [])
                    )
                    for item in gt_data
                    if item.get("query") or item.get("question")
                }
            else:
                ground_truth = gt_data
        logger.info(f"Loaded {len(ground_truth)} ground truth queries")
    else:
        logger.warning("No ground truth file - will measure overlap and latency only")

    # Default test queries (use ground truth keys if available)
    test_queries = (
        list(ground_truth.keys())[:20]  # Limit to 20 for reasonable test time
        if ground_truth
        else [
            "апартаменты в Солнечном берегу до 50000 евро",
            "студия с видом на море Несебр",
            "двухкомнатная квартира Бургас центр",
            "новостройка Святой Влас бассейн",
            "дом у моря Поморие",
            "недвижимость в Болгарии для инвестиций",
            "квартира первая линия моря",
            "жилье с паркингом рядом с пляжем",
        ]
    )

    results: dict[str, list[dict]] = {"baseline": [], "contextualized": []}

    for run in range(num_runs):
        logger.info(f"\n--- Run {run + 1}/{num_runs} ---")

        for query in test_queries:
            relevant_ids = ground_truth.get(query, [])

            # === BASELINE (standard Voyage embeddings) ===
            start = time.time()
            baseline_embedding = await baseline_voyage.embed_query(query)
            baseline_embed_time = time.time() - start

            start = time.time()
            baseline_results = await qdrant.hybrid_search_rrf(
                dense_vector=baseline_embedding,
                top_k=k,
            )
            baseline_search_time = time.time() - start

            baseline_latency = baseline_embed_time + baseline_search_time
            baseline_ids = [r.get("id", str(r.get("point_id", ""))) for r in baseline_results]

            # === CONTEXTUALIZED (voyage-context-3) ===
            start = time.time()
            ctx_embedding = await contextualized.embed_query(query)
            ctx_embed_time = time.time() - start

            start = time.time()
            ctx_results = await qdrant.hybrid_search_rrf(
                dense_vector=ctx_embedding,
                top_k=k,
            )
            ctx_search_time = time.time() - start

            ctx_latency = ctx_embed_time + ctx_search_time
            ctx_ids = [r.get("id", str(r.get("point_id", ""))) for r in ctx_results]

            # Calculate overlap between baseline and contextualized
            overlap = len(set(baseline_ids) & set(ctx_ids)) / k if k > 0 else 0

            results["baseline"].append(
                {
                    "query": query,
                    "latency": baseline_latency,
                    "embed_time": baseline_embed_time,
                    "search_time": baseline_search_time,
                    "ids": baseline_ids,
                    "precision": precision_at_k(baseline_ids, relevant_ids, k),
                    "recall": recall_at_k(baseline_ids, relevant_ids, k),
                }
            )

            results["contextualized"].append(
                {
                    "query": query,
                    "latency": ctx_latency,
                    "embed_time": ctx_embed_time,
                    "search_time": ctx_search_time,
                    "ids": ctx_ids,
                    "precision": precision_at_k(ctx_ids, relevant_ids, k),
                    "recall": recall_at_k(ctx_ids, relevant_ids, k),
                    "overlap_with_baseline": overlap,
                }
            )

    # Calculate aggregated metrics
    n = len(results["baseline"])

    # Latency metrics
    avg_latency_baseline = sum(r["latency"] for r in results["baseline"]) / n
    avg_latency_ctx = sum(r["latency"] for r in results["contextualized"]) / n
    avg_embed_baseline = sum(r["embed_time"] for r in results["baseline"]) / n
    avg_embed_ctx = sum(r["embed_time"] for r in results["contextualized"]) / n

    # Overlap metric
    avg_overlap = sum(r["overlap_with_baseline"] for r in results["contextualized"]) / n

    # Quality metrics
    avg_precision_baseline = sum(r["precision"] for r in results["baseline"]) / n
    avg_precision_ctx = sum(r["precision"] for r in results["contextualized"]) / n
    avg_recall_baseline = sum(r["recall"] for r in results["baseline"]) / n
    avg_recall_ctx = sum(r["recall"] for r in results["contextualized"]) / n

    # Print results
    print(f"\n{'=' * 70}")
    print(f"Contextualized Embeddings A/B Test Results (k={k}, runs={num_runs})")
    print("Model: voyage-context-3 vs baseline (voyage-3-large)")
    print(f"{'=' * 70}")

    print("\n  LATENCY:")
    print(f"  BASELINE:        {avg_latency_baseline * 1000:6.0f}ms avg total")
    print(f"    - Embedding:   {avg_embed_baseline * 1000:6.0f}ms")
    print(f"  CONTEXTUALIZED:  {avg_latency_ctx * 1000:6.0f}ms avg total")
    print(f"    - Embedding:   {avg_embed_ctx * 1000:6.0f}ms")

    latency_diff = (avg_latency_ctx - avg_latency_baseline) / avg_latency_baseline * 100
    print(f"  Latency diff:    {latency_diff:+.1f}%")

    print("\n  STABILITY (overlap with baseline):")
    print(f"  Avg top-{k} overlap:   {avg_overlap * 100:6.1f}%")

    if ground_truth:
        print("\n  QUALITY (vs ground truth):")
        print(f"  Precision@{k} BASELINE:      {avg_precision_baseline * 100:6.1f}%")
        print(f"  Precision@{k} CONTEXTUALIZED:{avg_precision_ctx * 100:6.1f}%")
        print(f"  Recall@{k} BASELINE:         {avg_recall_baseline * 100:6.1f}%")
        print(f"  Recall@{k} CONTEXTUALIZED:   {avg_recall_ctx * 100:6.1f}%")

        precision_delta = avg_precision_ctx - avg_precision_baseline
        recall_delta = avg_recall_ctx - avg_recall_baseline
        print(f"\n  Precision delta:      {precision_delta * 100:+6.1f}% ", end="")
        if precision_delta > 0.05:
            print("(improved!)")
        elif precision_delta < -0.05:
            print("(degradation!)")
        else:
            print("(stable)")

        print(f"  Recall delta:         {recall_delta * 100:+6.1f}% ", end="")
        if recall_delta > 0.05:
            print("(improved!)")
        elif recall_delta < -0.05:
            print("(degradation!)")
        else:
            print("(stable)")

    print(f"\n{'=' * 70}")

    # Thresholds check
    print("\n  PASS/FAIL CRITERIA:")
    checks = [
        ("Latency overhead <= 50%", latency_diff <= 50),
        ("Overlap >= 60%", avg_overlap >= 0.6),
    ]
    if ground_truth:
        # Contextualized should not degrade precision/recall by more than 10%
        checks.append(
            ("Precision delta >= -10%", avg_precision_ctx >= avg_precision_baseline - 0.1)
        )
        checks.append(("Recall delta >= -10%", avg_recall_ctx >= avg_recall_baseline - 0.1))

    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}]: {name}")
        all_pass = all_pass and passed

    print(f"\n{'=' * 70}")

    # Save detailed results to JSON
    output_file = Path("reports/contextualized_ab_results.json")
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(
            {
                "config": {
                    "k": k,
                    "runs": num_runs,
                    "output_dimension": output_dimension,
                    "queries_count": len(test_queries),
                },
                "summary": {
                    "baseline": {
                        "avg_latency_ms": avg_latency_baseline * 1000,
                        "avg_embed_ms": avg_embed_baseline * 1000,
                        "avg_precision": avg_precision_baseline,
                        "avg_recall": avg_recall_baseline,
                    },
                    "contextualized": {
                        "avg_latency_ms": avg_latency_ctx * 1000,
                        "avg_embed_ms": avg_embed_ctx * 1000,
                        "avg_precision": avg_precision_ctx,
                        "avg_recall": avg_recall_ctx,
                        "overlap_with_baseline": avg_overlap,
                    },
                },
                "all_pass": all_pass,
                "detailed_results": results,
            },
            f,
            indent=2,
        )
    logger.info(f"Detailed results saved to {output_file}")

    await qdrant.close()
    return all_pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A/B test for Voyage contextualized embeddings")
    parser.add_argument("--k", type=int, default=5, help="Top-k results to compare")
    parser.add_argument("--runs", type=int, default=1, help="Number of test runs")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("tests/eval/ground_truth.json"),
        help="Path to ground truth JSON file",
    )
    parser.add_argument(
        "--dim",
        type=int,
        default=1024,
        choices=[256, 512, 1024, 2048],
        help="Output embedding dimension",
    )
    args = parser.parse_args()

    success = asyncio.run(
        run_ab_test(
            k=args.k,
            num_runs=args.runs,
            ground_truth_path=args.ground_truth,
            output_dimension=args.dim,
        )
    )

    exit(0 if success else 1)
