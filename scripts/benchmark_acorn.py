#!/usr/bin/env python3
"""Microbenchmark: ACORN vs no-ACORN on filtered queries.

Compares latency and recall of filtered vector search with ACORN enabled vs disabled.

Usage:
    python scripts/benchmark_acorn.py --collection contextual_bulgaria_voyage
    python scripts/benchmark_acorn.py --iterations 50 --filter-field city --filter-value Несебр

Requirements:
    - Running Qdrant instance with data
    - Collection with payload fields for filtering
"""

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    mode: str  # "acorn" or "no_acorn"
    latencies_ms: list[float]
    result_counts: list[int]
    total_queries: int

    @property
    def mean_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p50_latency_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def mean_result_count(self) -> float:
        return statistics.mean(self.result_counts) if self.result_counts else 0.0

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "total_queries": self.total_queries,
            "mean_latency_ms": round(self.mean_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "mean_result_count": round(self.mean_result_count, 2),
        }


def generate_random_vector(dim: int = 1024) -> list[float]:
    """Generate a random normalized vector for testing."""
    import random

    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


def run_benchmark(
    client: QdrantClient,
    collection_name: str,
    query_filter: models.Filter,
    iterations: int,
    use_acorn: bool,
    acorn_max_selectivity: float = 0.4,
    top_k: int = 10,
) -> BenchmarkResult:
    """Run benchmark with or without ACORN.

    Args:
        client: Qdrant client instance.
        collection_name: Name of collection to search.
        query_filter: Filter to apply to queries.
        iterations: Number of queries to run.
        use_acorn: Whether to enable ACORN.
        acorn_max_selectivity: Max selectivity for ACORN.
        top_k: Number of results per query.

    Returns:
        BenchmarkResult with latency and result statistics.
    """
    mode = "acorn" if use_acorn else "no_acorn"
    latencies_ms = []
    result_counts = []

    # Build search params
    if use_acorn:
        search_params = models.SearchParams(
            acorn=models.AcornSearchParams(
                enable=True,
                max_selectivity=acorn_max_selectivity,
            )
        )
    else:
        search_params = models.SearchParams()

    for i in range(iterations):
        query_vector = generate_random_vector()

        start = time.perf_counter()
        results = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            search_params=search_params,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        latencies_ms.append(elapsed_ms)
        result_counts.append(len(results))

        if (i + 1) % 10 == 0:
            print(f"  {mode}: {i + 1}/{iterations} queries completed...")

    return BenchmarkResult(
        mode=mode,
        latencies_ms=latencies_ms,
        result_counts=result_counts,
        total_queries=iterations,
    )


def main():
    parser = argparse.ArgumentParser(description="ACORN benchmark for filtered queries")
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Qdrant server URL",
    )
    parser.add_argument(
        "--collection",
        default="gdrive_documents_bge",
        help="Collection name to benchmark",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=30,
        help="Number of queries per mode",
    )
    parser.add_argument(
        "--filter-field",
        default="metadata.city",
        help="Payload field to filter on",
    )
    parser.add_argument(
        "--filter-value",
        default="Несебр",
        help="Value to filter for",
    )
    parser.add_argument(
        "--acorn-max-selectivity",
        type=float,
        default=0.4,
        help="Max selectivity for ACORN",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results per query",
    )
    parser.add_argument(
        "--output",
        default="reports/acorn_benchmark.json",
        help="Output file for results",
    )
    args = parser.parse_args()

    print("ACORN Benchmark")
    print("===============")
    print(f"Collection: {args.collection}")
    print(f"Filter: {args.filter_field} = {args.filter_value}")
    print(f"Iterations: {args.iterations} per mode")
    print()

    # Connect to Qdrant
    client = QdrantClient(url=args.qdrant_url)

    # Verify collection exists
    try:
        info = client.get_collection(args.collection)
        print(f"Collection has {info.points_count} points")
    except Exception as e:
        print(f"Error: Cannot access collection '{args.collection}': {e}")
        sys.exit(1)

    # Build filter
    query_filter = models.Filter(
        must=[
            models.FieldCondition(
                key=args.filter_field,
                match=models.MatchValue(value=args.filter_value),
            )
        ]
    )

    print()
    print("Running benchmark WITHOUT ACORN...")
    result_no_acorn = run_benchmark(
        client=client,
        collection_name=args.collection,
        query_filter=query_filter,
        iterations=args.iterations,
        use_acorn=False,
        top_k=args.top_k,
    )

    print()
    print("Running benchmark WITH ACORN...")
    result_acorn = run_benchmark(
        client=client,
        collection_name=args.collection,
        query_filter=query_filter,
        iterations=args.iterations,
        use_acorn=True,
        acorn_max_selectivity=args.acorn_max_selectivity,
        top_k=args.top_k,
    )

    # Print results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()
    print(f"{'Metric':<25} {'No ACORN':<15} {'ACORN':<15} {'Diff':<15}")
    print("-" * 60)

    no_acorn = result_no_acorn.to_dict()
    acorn = result_acorn.to_dict()

    latency_diff = acorn["mean_latency_ms"] - no_acorn["mean_latency_ms"]
    latency_pct = (
        (latency_diff / no_acorn["mean_latency_ms"] * 100) if no_acorn["mean_latency_ms"] > 0 else 0
    )

    print(
        f"{'Mean Latency (ms)':<25} {no_acorn['mean_latency_ms']:<15.2f} {acorn['mean_latency_ms']:<15.2f} {latency_diff:+.2f} ({latency_pct:+.1f}%)"
    )
    print(
        f"{'P50 Latency (ms)':<25} {no_acorn['p50_latency_ms']:<15.2f} {acorn['p50_latency_ms']:<15.2f}"
    )
    print(
        f"{'P95 Latency (ms)':<25} {no_acorn['p95_latency_ms']:<15.2f} {acorn['p95_latency_ms']:<15.2f}"
    )

    results_diff = acorn["mean_result_count"] - no_acorn["mean_result_count"]
    print(
        f"{'Mean Result Count':<25} {no_acorn['mean_result_count']:<15.2f} {acorn['mean_result_count']:<15.2f} {results_diff:+.2f}"
    )

    print()

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "config": {
            "collection": args.collection,
            "filter_field": args.filter_field,
            "filter_value": args.filter_value,
            "iterations": args.iterations,
            "top_k": args.top_k,
            "acorn_max_selectivity": args.acorn_max_selectivity,
        },
        "results": {
            "no_acorn": no_acorn,
            "acorn": acorn,
        },
        "summary": {
            "latency_diff_ms": round(latency_diff, 2),
            "latency_diff_pct": round(latency_pct, 1),
            "results_diff": round(results_diff, 2),
        },
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Report saved to: {output_path}")

    # Return non-zero if ACORN significantly worse (> 50% latency increase with no recall improvement)
    if latency_pct > 50 and results_diff <= 0:
        print("\nWARNING: ACORN shows significant latency increase without recall improvement")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
