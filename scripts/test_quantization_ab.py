#!/usr/bin/env python3
"""A/B test for Qdrant Binary Quantization with precision@k metric.

Measures:
1. Latency: avg search time with/without quantization
2. Overlap: % of same results in top-k (stability metric)
3. Precision@k: % of relevant docs in top-k (quality metric)

Usage:
    python scripts/test_quantization_ab.py
    python scripts/test_quantization_ab.py --k 5 --runs 3
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from telegram_bot.config import BotConfig
from telegram_bot.services.qdrant import QdrantService
from telegram_bot.services.voyage import VoyageService


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
):
    """Run A/B test comparing quantization on/off."""
    config = BotConfig()

    voyage = VoyageService(api_key=config.voyage_api_key)
    qdrant = QdrantService(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection_name=config.qdrant_collection,
    )

    # Load ground truth if available
    ground_truth = {}
    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path) as f:
            gt_data = json.load(f)
            ground_truth = {item["query"]: item["relevant_ids"] for item in gt_data}
        print(f"Loaded {len(ground_truth)} ground truth queries")
    else:
        print("No ground truth file - will measure overlap only")

    # Default test queries (use ground truth keys if available)
    test_queries = (
        list(ground_truth.keys())
        if ground_truth
        else [
            "апартаменты в Солнечном берегу до 50000 евро",
            "студия с видом на море Несебр",
            "двухкомнатная квартира Бургас центр",
            "новостройка Святой Влас бассейн",
            "дом у моря Поморие",
        ]
    )

    results = {"with_quant": [], "without_quant": []}

    for run in range(num_runs):
        print(f"\n--- Run {run + 1}/{num_runs} ---")

        for query in test_queries:
            embedding = await voyage.embed_query(query)
            relevant_ids = ground_truth.get(query, [])

            # WITH quantization (default)
            start = time.time()
            r1 = await qdrant.hybrid_search_rrf(
                dense_vector=embedding,
                quantization_ignore=False,
                top_k=k,
            )
            latency_with = time.time() - start
            ids_with = [r["id"] for r in r1]

            # WITHOUT quantization (baseline)
            start = time.time()
            r2 = await qdrant.hybrid_search_rrf(
                dense_vector=embedding,
                quantization_ignore=True,
                top_k=k,
            )
            latency_without = time.time() - start
            ids_without = [r["id"] for r in r2]

            # Calculate metrics
            overlap = len(set(ids_with) & set(ids_without)) / k if k > 0 else 0

            results["with_quant"].append(
                {
                    "query": query,
                    "latency": latency_with,
                    "ids": ids_with,
                    "precision": precision_at_k(ids_with, relevant_ids, k),
                    "recall": recall_at_k(ids_with, relevant_ids, k),
                }
            )

            results["without_quant"].append(
                {
                    "query": query,
                    "latency": latency_without,
                    "ids": ids_without,
                    "precision": precision_at_k(ids_without, relevant_ids, k),
                    "recall": recall_at_k(ids_without, relevant_ids, k),
                    "overlap_with_quant": overlap,
                }
            )

    # Calculate aggregated metrics
    n = len(results["with_quant"])

    avg_latency_with = sum(r["latency"] for r in results["with_quant"]) / n
    avg_latency_without = sum(r["latency"] for r in results["without_quant"]) / n
    speedup = avg_latency_without / avg_latency_with if avg_latency_with > 0 else 0

    avg_overlap = sum(r["overlap_with_quant"] for r in results["without_quant"]) / n

    avg_precision_with = sum(r["precision"] for r in results["with_quant"]) / n
    avg_precision_without = sum(r["precision"] for r in results["without_quant"]) / n

    avg_recall_with = sum(r["recall"] for r in results["with_quant"]) / n
    avg_recall_without = sum(r["recall"] for r in results["without_quant"]) / n

    # Print results
    print(f"\n{'=' * 60}")
    print(f"Quantization A/B Test Results (k={k}, runs={num_runs})")
    print(f"{'=' * 60}")

    print("\n  LATENCY:")
    print(f"  WITH quantization:    {avg_latency_with * 1000:6.0f}ms avg")
    print(f"  WITHOUT quantization: {avg_latency_without * 1000:6.0f}ms avg")
    print(f"  Speedup:              {speedup:6.1f}x")

    print("\n  STABILITY (overlap with baseline):")
    print(f"  Avg top-{k} overlap:   {avg_overlap * 100:6.1f}%")

    if ground_truth:
        print("\n  QUALITY (vs ground truth):")
        print(f"  Precision@{k} WITH:    {avg_precision_with * 100:6.1f}%")
        print(f"  Precision@{k} WITHOUT: {avg_precision_without * 100:6.1f}%")
        print(f"  Recall@{k} WITH:       {avg_recall_with * 100:6.1f}%")
        print(f"  Recall@{k} WITHOUT:    {avg_recall_without * 100:6.1f}%")

        precision_delta = avg_precision_with - avg_precision_without
        print(f"\n  Precision delta:      {precision_delta * 100:+6.1f}% ", end="")
        if abs(precision_delta) < 0.05:
            print("(acceptable)")
        elif precision_delta < -0.1:
            print("(degradation!)")
        else:
            print("(improved)")

    print(f"\n{'=' * 60}")

    # Thresholds check
    print("\n  PASS/FAIL CRITERIA:")
    checks = [
        ("Speedup >= 2x", speedup >= 2.0),
        ("Overlap >= 80%", avg_overlap >= 0.8),
    ]
    if ground_truth:
        checks.append(
            ("Precision delta >= -10%", avg_precision_with >= avg_precision_without - 0.1)
        )

    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}]: {name}")
        all_pass = all_pass and passed

    print(f"\n{'=' * 60}\n")

    await qdrant.close()
    return all_pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A/B test for Qdrant quantization")
    parser.add_argument("--k", type=int, default=5, help="Top-k results to compare")
    parser.add_argument("--runs", type=int, default=1, help="Number of test runs")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("scripts/ground_truth_queries.json"),
        help="Path to ground truth JSON file",
    )
    args = parser.parse_args()

    success = asyncio.run(
        run_ab_test(
            k=args.k,
            num_runs=args.runs,
            ground_truth_path=args.ground_truth,
        )
    )

    exit(0 if success else 1)
