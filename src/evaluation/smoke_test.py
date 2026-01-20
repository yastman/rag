#!/usr/bin/env python3
"""
Smoke Test Runner - Quick Regression Testing

30 carefully selected "hard" queries for rapid quality checks before deployment.

Target SLO:
    - Precision@1 ≥ 90%
    - Recall@10 ≥ 95%
    - p95 latency < 800ms
    - Zero failures

Usage:
    python smoke_test.py --engine dbsf_colbert
    python smoke_test.py --engine baseline --quick

Integration with CI/CD:
    # .github/workflows/test.yml
    - name: Run smoke test
      run: python evaluation/smoke_test.py --strict
      # Exit code 1 if SLO violated
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any


# Import search engines and evaluator
sys.path.insert(0, str(Path(__file__).parent))
from config_snapshot import get_config_hash
from search_engines import (
    BaselineSearchEngine,
    HybridDBSFColBERTSearchEngine,
    HybridSearchEngine,
)


# Smoke test queries: 30 carefully selected queries
# Mix of difficulties: 10 hard, 10 medium, 10 easy
SMOKE_QUERIES = [
    # HARD queries (10) - complex, multi-hop, paraphrased
    {
        "id": 1,
        "query": "что регулирует первая статья УК Украины о правовом обеспечении",
        "expected_article": "1",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 2,
        "query": "как учитывается иностранный приговор при рецидиве на территории Украины?",
        "expected_article": "9",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 3,
        "query": "какая уголовная ответственность за отказ от дальнейшего совершения преступления по собственной воле",
        "expected_article": "17",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 4,
        "query": "как определяется неосторожность: предвидел или не предвидел последствия действий",
        "expected_article": "25",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 5,
        "query": "как квалифицировать два разных преступления, совершённые одним лицом одновременно",
        "expected_article": "33",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 6,
        "query": "какая ответственность за исполнение явно преступного приказа или распоряжения",
        "expected_article": "41",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 7,
        "query": "когда преступление считается погашенным по истечении 10 лет",
        "expected_article": "49",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 8,
        "query": "можно ли заменить исправительные работы штрафом при нетрудоспособности осуждённого",
        "expected_article": "57",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    {
        "id": 9,
        "query": "какие основания для более мягкого наказания по УК Украины",
        "expected_article": "65",
        "difficulty": "hard",
        "type": "semantic",
    },
    {
        "id": 10,
        "query": "можно ли учитывать дни при замене или сложении наказаний?",
        "expected_article": "73",
        "difficulty": "hard",
        "type": "paraphrased",
    },
    # MEDIUM queries (10) - semantic understanding required
    {
        "id": 11,
        "query": "какие цели и задачи ставит перед собой уголовный кодекс Украины",
        "expected_article": "1",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 12,
        "query": "учет приговора иностранного государства при повторном преступлении в Украине",
        "expected_article": "9",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 13,
        "query": "что подразумевается под добровольным отказом от доведения преступления до конца",
        "expected_article": "17",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 14,
        "query": "что такое преступная самоуверенность и преступная небрежность по УК Украины",
        "expected_article": "25",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 15,
        "query": "что считается совокупностью нескольких преступлений по УК",
        "expected_article": "33",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 16,
        "query": "когда действие по приказу считается правомерным по УК",
        "expected_article": "41",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 17,
        "query": "какие сроки давности освобождают от уголовной ответственности",
        "expected_article": "49",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 18,
        "query": "какое наказание предусматривается исправительными работами и каков максимальный срок",
        "expected_article": "57",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 19,
        "query": "как суд назначает наказание с учётом тяжести преступления",
        "expected_article": "65",
        "difficulty": "medium",
        "type": "semantic",
    },
    {
        "id": 20,
        "query": "как рассчитываются сроки наказания в годах, месяцах и днях",
        "expected_article": "73",
        "difficulty": "medium",
        "type": "semantic",
    },
    # EASY queries (10) - direct article mentions
    {
        "id": 21,
        "query": "статья 1 Уголовного кодекса Украины задачи",
        "expected_article": "1",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 22,
        "query": "статья 9 УК Украины правовые последствия осуждения за границей",
        "expected_article": "9",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 23,
        "query": "статья 17 добровольный отказ при неоконченном преступлении",
        "expected_article": "17",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 24,
        "query": "статья 25 неосторожность уголовный кодекс Украины",
        "expected_article": "25",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 25,
        "query": "статья 33 совокупность преступлений Украины",
        "expected_article": "33",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 26,
        "query": "статья 41 Уголовного кодекса Украины исполнение приказа",
        "expected_article": "41",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 27,
        "query": "статья 49 Уголовного кодекса Украины сроки давности",
        "expected_article": "49",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 28,
        "query": "статья 57 УК Украины исправительные работы",
        "expected_article": "57",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 29,
        "query": "статья 65 Уголовного кодекса Украины",
        "expected_article": "65",
        "difficulty": "easy",
        "type": "direct",
    },
    {
        "id": 30,
        "query": "статья 73 УК Украины исчисление сроков наказания",
        "expected_article": "73",
        "difficulty": "easy",
        "type": "direct",
    },
]

# SLO thresholds
SLO_THRESHOLDS = {
    "precision_at_1_min": 0.90,  # 90% minimum
    "recall_at_10_min": 0.95,  # 95% minimum
    "p95_latency_ms_max": 800,  # 800ms maximum
    "p99_latency_ms_max": 1200,  # 1200ms maximum
    "failure_rate_max": 0.0,  # Zero failures allowed
}


def run_smoke_test(
    engine_name: str = "dbsf_colbert",
    collection: str = "uk_civil_code_v2",
    strict: bool = False,
    quick: bool = False,
) -> dict[str, Any]:
    """
    Run smoke test on specified search engine.

    Args:
        engine_name: Search engine to test (baseline, hybrid, dbsf_colbert)
        collection: Qdrant collection name
        strict: If True, exit with code 1 on SLO violation
        quick: If True, run only 10 queries (fastest mode)

    Returns:
        Dictionary with test results
    """
    print("=" * 80)
    print("🔥 SMOKE TEST - Quick Regression Check")
    print("=" * 80)
    print("\n📋 Configuration:")
    print(f"   Engine: {engine_name}")
    print(f"   Collection: {collection}")
    print(f"   Config Hash: {get_config_hash()}")
    print(f"   Queries: {10 if quick else 30}")
    print(f"   Strict Mode: {strict}")

    # Initialize engine
    print(f"\n🔧 Initializing {engine_name} engine...")
    if engine_name == "baseline":
        engine = BaselineSearchEngine(collection_name=collection)
    elif engine_name == "hybrid":
        engine = HybridSearchEngine(collection_name=collection)
    elif engine_name == "dbsf_colbert":
        engine = HybridDBSFColBERTSearchEngine(collection_name=collection)
    else:
        raise ValueError(f"Unknown engine: {engine_name}")

    # Run queries
    queries = SMOKE_QUERIES[:10] if quick else SMOKE_QUERIES
    results = []
    latencies = []

    print(f"\n🏃 Running {len(queries)} smoke queries...")
    for i, query_data in enumerate(queries, 1):
        query = query_data["query"]
        expected = int(query_data["expected_article"])  # type: ignore[call-overload]

        start_time = time.time()
        search_results = engine.search(query, limit=10)
        latency_ms = (time.time() - start_time) * 1000
        latencies.append(latency_ms)

        # Check if expected article in results
        retrieved_articles = [int(r.payload.get("article_number", 0)) for r in search_results]
        precision_at_1 = 1.0 if retrieved_articles and retrieved_articles[0] == expected else 0.0
        recall_at_10 = 1.0 if expected in retrieved_articles else 0.0

        results.append(
            {
                "query_id": query_data["id"],
                "difficulty": query_data["difficulty"],
                "precision_at_1": precision_at_1,
                "recall_at_10": recall_at_10,
                "latency_ms": latency_ms,
            }
        )

        status = "✅" if precision_at_1 == 1.0 else "❌"
        print(
            f"   [{i:2d}/{len(queries)}] {status} "
            f"P@1={precision_at_1:.0%} R@10={recall_at_10:.0%} "
            f"{latency_ms:5.0f}ms - {query[:60]}..."  # type: ignore
        )

    # Calculate metrics
    avg_precision_at_1 = sum(r["precision_at_1"] for r in results) / len(results)  # type: ignore
    avg_recall_at_10 = sum(r["recall_at_10"] for r in results) / len(results)  # type: ignore
    failure_rate = 1.0 - avg_recall_at_10

    latencies_sorted = sorted(latencies)
    p50_latency = latencies_sorted[len(latencies_sorted) // 2]
    p95_latency = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99_latency = latencies_sorted[int(len(latencies_sorted) * 0.99)]

    # Print results
    print("\n" + "=" * 80)
    print("📊 SMOKE TEST RESULTS")
    print("=" * 80)

    print("\n🎯 Quality Metrics:")
    print(
        f"   Precision@1: {avg_precision_at_1:.1%} (target: ≥{SLO_THRESHOLDS['precision_at_1_min']:.0%})"
    )
    print(
        f"   Recall@10:   {avg_recall_at_10:.1%} (target: ≥{SLO_THRESHOLDS['recall_at_10_min']:.0%})"
    )
    print(
        f"   Failure Rate: {failure_rate:.1%} (target: ≤{SLO_THRESHOLDS['failure_rate_max']:.0%})"
    )

    print("\n⏱️  Latency Metrics:")
    print(f"   p50: {p50_latency:6.0f}ms")
    print(f"   p95: {p95_latency:6.0f}ms (target: ≤{SLO_THRESHOLDS['p95_latency_ms_max']}ms)")
    print(f"   p99: {p99_latency:6.0f}ms (target: ≤{SLO_THRESHOLDS['p99_latency_ms_max']}ms)")

    # Check SLO violations
    violations = []
    if avg_precision_at_1 < SLO_THRESHOLDS["precision_at_1_min"]:
        violations.append(f"Precision@1 too low: {avg_precision_at_1:.1%}")
    if avg_recall_at_10 < SLO_THRESHOLDS["recall_at_10_min"]:
        violations.append(f"Recall@10 too low: {avg_recall_at_10:.1%}")
    if p95_latency > SLO_THRESHOLDS["p95_latency_ms_max"]:
        violations.append(f"p95 latency too high: {p95_latency:.0f}ms")
    if failure_rate > SLO_THRESHOLDS["failure_rate_max"]:
        violations.append(f"Failure rate too high: {failure_rate:.1%}")

    if violations:
        print("\n❌ SLO VIOLATIONS:")
        for violation in violations:
            print(f"   - {violation}")
        if strict:
            print("\n🚨 Strict mode: Exiting with error code 1")
            sys.exit(1)
    else:
        print("\n✅ ALL SLO CHECKS PASSED!")

    # Breakdown by difficulty
    print("\n📈 Breakdown by Difficulty:")
    for difficulty in ["easy", "medium", "hard"]:
        diff_results = [r for r in results if r["difficulty"] == difficulty]
        if diff_results:
            diff_p1 = sum(r["precision_at_1"] for r in diff_results) / len(diff_results)  # type: ignore
            print(f"   {difficulty.capitalize():6s}: {diff_p1:.1%} ({len(diff_results)} queries)")

    print("\n" + "=" * 80)

    return {
        "engine": engine_name,
        "collection": collection,
        "config_hash": get_config_hash(),
        "queries_count": len(queries),
        "precision_at_1": avg_precision_at_1,
        "recall_at_10": avg_recall_at_10,
        "failure_rate": failure_rate,
        "latency_p50_ms": p50_latency,
        "latency_p95_ms": p95_latency,
        "latency_p99_ms": p99_latency,
        "slo_violations": violations,
        "passed": len(violations) == 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run smoke test for regression testing")
    parser.add_argument(
        "--engine",
        choices=["baseline", "hybrid", "dbsf_colbert"],
        default="dbsf_colbert",
        help="Search engine to test",
    )
    parser.add_argument(
        "--collection",
        default="uk_civil_code_v2",
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 on SLO violation (for CI/CD)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only 10 queries (fastest mode)",
    )

    args = parser.parse_args()

    result = run_smoke_test(
        engine_name=args.engine,
        collection=args.collection,
        strict=args.strict,
        quick=args.quick,
    )

    # Exit with appropriate code
    sys.exit(0 if result["passed"] else 1)
