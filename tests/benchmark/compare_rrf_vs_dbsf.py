#!/usr/bin/env python3
"""
Direct A/B comparison between Variant A (RRF) and Variant B (DBSF).
Runs the same queries through both engines and compares results.
"""

import sys
import time
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import Settings
from src.retrieval import DBSFColBERTSearchEngine, HybridRRFColBERTSearchEngine


def compare_engines():
    """Compare RRF vs DBSF on identical queries."""

    print("=" * 80)
    print("A/B TEST: VARIANT A (RRF) vs VARIANT B (DBSF)")
    print("=" * 80)

    # Initialize settings
    settings = Settings()
    print("\n📋 Configuration:")
    print(f"   Qdrant URL: {settings.qdrant_url}")
    print(f"   Collection: {settings.collection_name}")

    # Initialize both engines
    print("\n🔧 Initializing search engines...")
    rrf_engine = HybridRRFColBERTSearchEngine(settings)
    print("   ✅ Variant A (RRF) initialized")
    dbsf_engine = DBSFColBERTSearchEngine(settings)
    print("   ✅ Variant B (DBSF) initialized")

    # Test queries
    test_queries = [
        ("Стаття 121 Кримінального кодексу", "Article lookup"),
        ("Умисне вбивство з особливою жорстокістю", "Crime with qualifier"),
        ("Коли застосовується крайня необхідність?", "Legal concept"),
    ]

    comparison_results = []

    for i, (query, description) in enumerate(test_queries, 1):
        print(f"\n{'=' * 80}")
        print(f"🔍 Query {i}: {query}")
        print(f"   Type: {description}")
        print(f"{'=' * 80}")

        # Run Variant A (RRF)
        print("\n🅰️  Variant A (RRF + ColBERT):")
        try:
            start_time = time.time()
            rrf_results = rrf_engine.search(
                query_embedding=query,
                top_k=5,
                score_threshold=0.3,
            )
            rrf_time = time.time() - start_time

            print(f"   Time: {rrf_time:.3f}s")
            print(f"   Results: {len(rrf_results)}")
            for j, r in enumerate(rrf_results, 1):
                print(f"      {j}. Article {r.article_number}: {r.score:.4f}")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            rrf_results = []
            rrf_time = 0

        # Run Variant B (DBSF)
        print("\n🅱️  Variant B (DBSF + ColBERT):")
        try:
            start_time = time.time()
            dbsf_results = dbsf_engine.search(
                query_embedding=query,
                top_k=5,
                score_threshold=0.3,
            )
            dbsf_time = time.time() - start_time

            print(f"   Time: {dbsf_time:.3f}s")
            print(f"   Results: {len(dbsf_results)}")
            for j, r in enumerate(dbsf_results, 1):
                print(f"      {j}. Article {r.article_number}: {r.score:.4f}")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            dbsf_results = []
            dbsf_time = 0

        # Compare results
        print("\n📊 Comparison:")
        if rrf_results and dbsf_results:
            # Compare top result
            rrf_top = rrf_results[0].article_number
            dbsf_top = dbsf_results[0].article_number
            print("   Top Result:")
            print(f"      RRF:  Article {rrf_top}")
            print(f"      DBSF: Article {dbsf_top}")
            if rrf_top == dbsf_top:
                print("      ✅ Same top result")
            else:
                print("      ⚠️  Different top results")

            # Compare ranking overlap
            rrf_articles = {r.article_number for r in rrf_results}
            dbsf_articles = {r.article_number for r in dbsf_results}
            overlap = len(rrf_articles & dbsf_articles)
            print(f"   Overlap: {overlap}/5 articles in common")

            # Compare latency
            if abs(rrf_time - dbsf_time) < 0.1:
                print(f"   Latency: ~Equal ({rrf_time:.3f}s vs {dbsf_time:.3f}s)")
            elif rrf_time < dbsf_time:
                print(f"   Latency: RRF faster ({rrf_time:.3f}s vs {dbsf_time:.3f}s)")
            else:
                print(f"   Latency: DBSF faster ({rrf_time:.3f}s vs {dbsf_time:.3f}s)")

            # Compare scores
            print("   Score ranges:")
            rrf_min, rrf_max = min(r.score for r in rrf_results), max(r.score for r in rrf_results)
            dbsf_min, dbsf_max = (
                min(r.score for r in dbsf_results),
                max(r.score for r in dbsf_results),
            )
            print(f"      RRF:  [{rrf_min:.4f}, {rrf_max:.4f}]")
            print(f"      DBSF: [{dbsf_min:.4f}, {dbsf_max:.4f}]")

        comparison_results.append(
            {
                "query": query,
                "rrf": {
                    "top_article": rrf_results[0].article_number if rrf_results else None,
                    "articles": [r.article_number for r in rrf_results],
                    "scores": [r.score for r in rrf_results],
                    "time": rrf_time,
                },
                "dbsf": {
                    "top_article": dbsf_results[0].article_number if dbsf_results else None,
                    "articles": [r.article_number for r in dbsf_results],
                    "scores": [r.score for r in dbsf_results],
                    "time": dbsf_time,
                },
            }
        )

    # Final summary
    print(f"\n{'=' * 80}")
    print("📈 OVERALL COMPARISON SUMMARY")
    print("=" * 80)

    # Count same top results
    same_top = sum(
        1 for r in comparison_results if r["rrf"]["top_article"] == r["dbsf"]["top_article"]
    )
    print(f"\nTop Result Agreement: {same_top}/{len(test_queries)} queries")

    # Average latency
    avg_rrf_time = sum(r["rrf"]["time"] for r in comparison_results) / len(comparison_results)
    avg_dbsf_time = sum(r["dbsf"]["time"] for r in comparison_results) / len(comparison_results)
    print("\nAverage Latency:")
    print(f"   RRF:  {avg_rrf_time:.3f}s")
    print(f"   DBSF: {avg_dbsf_time:.3f}s")
    if abs(avg_rrf_time - avg_dbsf_time) < 0.05:
        print("   ✅ Latency is comparable")
    elif avg_rrf_time < avg_dbsf_time:
        diff_pct = ((avg_dbsf_time - avg_rrf_time) / avg_rrf_time) * 100
        print(f"   ⚠️  RRF is {diff_pct:.1f}% faster")
    else:
        diff_pct = ((avg_rrf_time - avg_dbsf_time) / avg_dbsf_time) * 100
        print(f"   ✅ DBSF is {diff_pct:.1f}% faster")

    # Conclusion
    print(f"\n{'=' * 80}")
    print("🎯 CONCLUSION")
    print("=" * 80)
    if same_top == len(test_queries):
        print("✅ Both fusion methods produce identical top results")
        print("   Recommendation: Use RRF (simpler, proven, de facto standard)")
    elif same_top >= len(test_queries) * 0.7:
        print("⚠️  Fusion methods produce similar but not identical results")
        print("   Recommendation: A/B test in production to compare user satisfaction")
    else:
        print("⚠️  Fusion methods produce significantly different results")
        print("   Recommendation: Evaluate which method aligns better with ground truth")

    print(f"{'=' * 80}\n")

    # Save comparison results
    import json

    output_path = Path(__file__).parent / "comparison_rrf_vs_dbsf.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison_results, f, indent=2, ensure_ascii=False)
    print(f"💾 Results saved to: {output_path}\n")

    return comparison_results


if __name__ == "__main__":
    try:
        results = compare_engines()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Comparison failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
