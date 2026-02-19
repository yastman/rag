#!/usr/bin/env python3
"""A/B test: INT8 (Scalar) vs Binary Quantization.

Compares two collections with different quantization strategies:
- *_scalar: INT8 quantization (4x compression, better accuracy)
- *_binary: Binary quantization (32x compression, faster search)

Measures:
1. Latency: avg search time per quantization type
2. Recall@k: overlap with unquantized baseline
3. Precision@k: if ground truth available

Tests different oversampling factors (2.0, 3.0, 4.0) to find optimal settings.

Usage:
    python scripts/test_int8_vs_binary.py
    python scripts/test_int8_vs_binary.py --base contextual_bulgaria_voyage
    python scripts/test_int8_vs_binary.py --k 10 --runs 3
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from qdrant_client import AsyncQdrantClient, models


@dataclass
class SearchMetrics:
    """Metrics for a single search configuration."""

    quant_type: str
    oversampling: float
    latencies_ms: list[float] = field(default_factory=list)
    overlaps: list[float] = field(default_factory=list)
    precisions: list[float] = field(default_factory=list)
    recalls: list[float] = field(default_factory=list)

    @property
    def avg_latency(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0

    @property
    def avg_overlap(self) -> float:
        return sum(self.overlaps) / len(self.overlaps) if self.overlaps else 0

    @property
    def avg_precision(self) -> float:
        return sum(self.precisions) / len(self.precisions) if self.precisions else 0

    @property
    def avg_recall(self) -> float:
        return sum(self.recalls) / len(self.recalls) if self.recalls else 0


def get_collection_names(base: str) -> dict[str, str]:
    """Get collection names for different quantization types."""
    # Strip existing suffixes
    for suffix in ["_binary", "_scalar"]:
        base = base.removesuffix(suffix)
    return {
        "baseline": base,  # Original (may have binary quant, but we'll use ignore=True)
        "scalar": f"{base}_scalar",
        "binary": f"{base}_binary",
    }


async def search_with_quantization(
    client: AsyncQdrantClient,
    collection_name: str,
    query_vector: list[float],
    top_k: int,
    rescore: bool = True,
    oversampling: float = 2.0,
    ignore_quant: bool = False,
) -> tuple[list[str], float]:
    """Search with specific quantization settings.

    Returns:
        Tuple of (result_ids, latency_ms)
    """
    search_params = models.SearchParams(
        quantization=models.QuantizationSearchParams(
            ignore=ignore_quant,
            rescore=rescore,
            oversampling=oversampling,
        )
    )

    start = time.perf_counter()
    result = await client.query_points(
        collection_name=collection_name,
        query=query_vector,
        using="dense",
        limit=top_k,
        with_payload=True,
        search_params=search_params,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    ids = [str(p.id) for p in result.points]
    return ids, latency_ms


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Calculate Precision@K."""
    if not relevant or k == 0:
        return 0.0
    retrieved_k = set(retrieved[:k])
    relevant_set = set(relevant)
    return len(retrieved_k & relevant_set) / k


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Calculate Recall@K."""
    if not relevant:
        return 0.0
    retrieved_k = set(retrieved[:k])
    relevant_set = set(relevant)
    return len(retrieved_k & relevant_set) / len(relevant_set)


def overlap_at_k(retrieved1: list[str], retrieved2: list[str], k: int) -> float:
    """Calculate overlap between two result sets."""
    if k == 0:
        return 0.0
    set1 = set(retrieved1[:k])
    set2 = set(retrieved2[:k])
    return len(set1 & set2) / k


async def run_ab_test(
    base_collection: str,
    k: int = 5,
    num_runs: int = 1,
    oversampling_factors: list[float] | None = None,
    ground_truth_path: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    """Run A/B test comparing INT8 vs Binary quantization.

    Args:
        base_collection: Base collection name (without suffix)
        k: Top-k results to compare
        num_runs: Number of test runs
        oversampling_factors: List of oversampling factors to test
        ground_truth_path: Optional path to ground truth JSON
        output_path: Optional path to save results JSON

    Returns:
        Dict with test results
    """
    if oversampling_factors is None:
        oversampling_factors = [2.0, 3.0, 4.0]

    # Setup
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")
    client = AsyncQdrantClient(url=url, api_key=api_key)

    collections = get_collection_names(base_collection)
    print(f"Collections: {collections}")

    # Check collections exist
    for name, coll in collections.items():
        try:
            info = await client.get_collection(coll)
            print(f"  {name}: {coll} ({info.points_count} points)")
        except Exception as e:
            print(f"  Warning: Collection {coll} not found: {e}")
            if name != "baseline":
                print(f"  Skipping {name} collection")
                collections[name] = None

    # Load ground truth
    ground_truth = {}
    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path) as f:
            gt_data = json.load(f)
            ground_truth = {item["query"]: item.get("relevant_ids", []) for item in gt_data}
        print(f"Loaded {len(ground_truth)} ground truth queries")

    # Test queries (with embeddings)
    test_queries_path = Path("scripts/test_embeddings.json")
    if test_queries_path.exists():
        with open(test_queries_path) as f:
            test_data = json.load(f)
    else:
        # Generate test embeddings from first N points in baseline collection
        print("Generating test queries from collection...")
        points = await client.scroll(
            collection_name=collections["baseline"],
            limit=10,
            with_vectors=True,
        )
        test_data = [
            {
                "query": p.payload.get("page_content", "")[:100] if p.payload else f"query_{i}",
                "embedding": p.vector["dense"] if isinstance(p.vector, dict) else p.vector,
            }
            for i, p in enumerate(points[0])
            if p.vector
        ]

    print(f"Running tests with {len(test_data)} queries, k={k}, runs={num_runs}")

    # Initialize metrics storage
    metrics: dict[str, dict[float, SearchMetrics]] = {
        "scalar": {},
        "binary": {},
    }
    for quant_type in metrics:
        for osf in oversampling_factors:
            metrics[quant_type][osf] = SearchMetrics(quant_type=quant_type, oversampling=osf)

    # Run tests
    for run in range(num_runs):
        print(f"\n--- Run {run + 1}/{num_runs} ---")

        for query_data in test_data:
            query = query_data.get("query", "unknown")
            embedding = query_data.get("embedding")

            if not embedding:
                print(f"  Skipping query without embedding: {query[:30]}...")
                continue

            # Get baseline results (ignore quantization)
            baseline_ids, _ = await search_with_quantization(
                client,
                collections["baseline"],
                embedding,
                k,
                ignore_quant=True,
            )

            relevant_ids = ground_truth.get(query, [])

            # Test each quantization type and oversampling factor
            for quant_type, coll_name in [
                ("scalar", collections["scalar"]),
                ("binary", collections["binary"]),
            ]:
                if not coll_name:
                    continue

                for osf in oversampling_factors:
                    try:
                        result_ids, latency = await search_with_quantization(
                            client,
                            coll_name,
                            embedding,
                            k,
                            rescore=True,
                            oversampling=osf,
                        )

                        m = metrics[quant_type][osf]
                        m.latencies_ms.append(latency)
                        m.overlaps.append(overlap_at_k(result_ids, baseline_ids, k))

                        if relevant_ids:
                            m.precisions.append(precision_at_k(result_ids, relevant_ids, k))
                            m.recalls.append(recall_at_k(result_ids, relevant_ids, k))

                    except Exception as e:
                        print(f"  Error testing {quant_type} osf={osf}: {e}")

    await client.close()

    # Generate report
    results = {
        "config": {
            "base_collection": base_collection,
            "k": k,
            "num_runs": num_runs,
            "oversampling_factors": oversampling_factors,
            "num_queries": len(test_data),
            "has_ground_truth": bool(ground_truth),
        },
        "metrics": {},
    }

    print(f"\n{'=' * 70}")
    print(f"INT8 vs Binary Quantization A/B Test Results (k={k}, runs={num_runs})")
    print(f"{'=' * 70}")

    print("\n  LATENCY (ms):")
    print(f"  {'Type':<10} {'OSF':>6} {'Avg':>10} {'vs Baseline':>15}")
    print("  " + "-" * 45)

    best_config = {"type": None, "osf": None, "score": 0}

    for quant_type in ["scalar", "binary"]:
        results["metrics"][quant_type] = {}

        for osf in oversampling_factors:
            m = metrics[quant_type][osf]
            if not m.latencies_ms:
                continue

            results["metrics"][quant_type][str(osf)] = {
                "avg_latency_ms": round(m.avg_latency, 2),
                "avg_overlap": round(m.avg_overlap, 4),
                "avg_precision": round(m.avg_precision, 4) if m.precisions else None,
                "avg_recall": round(m.avg_recall, 4) if m.recalls else None,
                "num_samples": len(m.latencies_ms),
            }

            # Calculate composite score (higher is better)
            # Balance: 40% overlap, 30% latency (inverse), 30% precision
            latency_score = max(0, 1 - m.avg_latency / 100)  # Normalize to 0-1
            score = 0.4 * m.avg_overlap + 0.3 * latency_score
            if m.avg_precision:
                score += 0.3 * m.avg_precision

            if score > best_config["score"]:
                best_config = {"type": quant_type, "osf": osf, "score": score}

            print(f"  {quant_type:<10} {osf:>6.1f} {m.avg_latency:>10.1f}")

    print("\n  OVERLAP WITH BASELINE:")
    print(f"  {'Type':<10} {'OSF':>6} {'Overlap':>10}")
    print("  " + "-" * 30)

    for quant_type in ["scalar", "binary"]:
        for osf in oversampling_factors:
            m = metrics[quant_type][osf]
            if m.overlaps:
                print(f"  {quant_type:<10} {osf:>6.1f} {m.avg_overlap * 100:>9.1f}%")

    if ground_truth:
        print("\n  PRECISION@K (vs ground truth):")
        print(f"  {'Type':<10} {'OSF':>6} {'Precision':>10} {'Recall':>10}")
        print("  " + "-" * 40)

        for quant_type in ["scalar", "binary"]:
            for osf in oversampling_factors:
                m = metrics[quant_type][osf]
                if m.precisions:
                    print(
                        f"  {quant_type:<10} {osf:>6.1f} {m.avg_precision * 100:>9.1f}% {m.avg_recall * 100:>9.1f}%"
                    )

    print(f"\n{'=' * 70}")
    print("  RECOMMENDATION:")
    if best_config["type"]:
        print(
            f"  Best configuration: {best_config['type'].upper()} with oversampling={best_config['osf']}"
        )
        print(f"  Composite score: {best_config['score']:.3f}")
    else:
        print("  No configuration tested successfully")
    print(f"{'=' * 70}\n")

    results["recommendation"] = best_config

    # Save results
    if output_path:
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {output_path}")

    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="A/B test: INT8 (Scalar) vs Binary Quantization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  QDRANT_URL      Qdrant server URL (default: http://localhost:6333)
  QDRANT_API_KEY  Optional API key for authentication

Examples:
  python scripts/test_int8_vs_binary.py
  python scripts/test_int8_vs_binary.py --base contextual_bulgaria_voyage
  python scripts/test_int8_vs_binary.py --k 10 --runs 3 --output report.json
        """,
    )

    parser.add_argument(
        "--base",
        "-b",
        default=os.getenv("COLLECTION_NAME", "gdrive_documents_bge"),
        help="Base collection name (without _scalar/_binary suffix)",
    )

    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Top-k results to compare (default: 5)",
    )

    parser.add_argument(
        "--runs",
        "-r",
        type=int,
        default=1,
        help="Number of test runs (default: 1)",
    )

    parser.add_argument(
        "--oversampling",
        "-o",
        type=float,
        nargs="+",
        default=[2.0, 3.0, 4.0],
        help="Oversampling factors to test (default: 2.0 3.0 4.0)",
    )

    parser.add_argument(
        "--ground-truth",
        "-g",
        type=Path,
        default=Path("scripts/ground_truth_queries.json"),
        help="Path to ground truth JSON file",
    )

    parser.add_argument(
        "--output",
        "-O",
        type=Path,
        default=Path("reports/quantization_ab_report.json"),
        help="Path to save results JSON",
    )

    args = parser.parse_args()

    # Ensure output directory exists
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("INT8 vs Binary Quantization A/B Test")
    print("=" * 70 + "\n")

    results = asyncio.run(
        run_ab_test(
            base_collection=args.base,
            k=args.k,
            num_runs=args.runs,
            oversampling_factors=args.oversampling,
            ground_truth_path=args.ground_truth,
            output_path=args.output,
        )
    )

    # Return success if any metrics were collected
    has_metrics = any(
        any(m for m in type_metrics.values())
        for type_metrics in results.get("metrics", {}).values()
    )

    return 0 if has_metrics else 1


if __name__ == "__main__":
    sys.exit(main())
