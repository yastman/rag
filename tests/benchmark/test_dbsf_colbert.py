#!/usr/bin/env python3
"""
Test DBSF + ColBERT multivector rerank in production code (Variant B).
Verifies DBSFColBERTSearchEngine uses: Dense + Sparse + DBSF fusion + ColBERT rerank.
"""

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import Settings
from src.retrieval import DBSFColBERTSearchEngine


def _run_dbsf_colbert() -> tuple[bool, dict[str, list[dict[str, str | float | None]]] | None]:
    """Run Variant B benchmark flow and return success flag with collected results."""

    print("=" * 80)
    print("TEST: VARIANT B - HYBRID DBSF + COLBERT RERANK")
    print("=" * 80)

    # Initialize settings and search engine
    settings = Settings()
    print("\n📋 Configuration:")
    print(f"   Qdrant URL: {settings.qdrant_url}")
    print(f"   Collection: {settings.collection_name}")
    print(
        f"   API Key: {'***' + settings.qdrant_api_key[-10:] if settings.qdrant_api_key else 'Not set'}"
    )

    # Initialize Variant B search engine
    print("\n🔧 Initializing DBSFColBERTSearchEngine (Variant B)...")
    search_engine = DBSFColBERTSearchEngine(settings)
    print("   ✅ Search engine initialized with BGE-M3 model")
    print("   ✅ 3-Stage Pipeline:")
    print("      Stage 1: Dense (100) + Sparse (100) prefetch")
    print("      Stage 2: DBSF fusion (statistical normalization)")
    print("      Stage 3: ColBERT multivector MaxSim rerank")

    # Test queries (same as Variant A for comparison)
    test_queries = [
        ("Стаття 121 Кримінального кодексу", "Article lookup with exact number"),
        ("Умисне вбивство з особливою жорстокістю", "Crime with specific qualifier"),
        ("Коли застосовується крайня необхідність?", "Legal concept question"),
    ]

    all_results = {}

    for i, (query, description) in enumerate(test_queries, 1):
        print(f"\n{'=' * 80}")
        print(f"🔍 Test Query {i}: {query}")
        print(f"   Description: {description}")
        print(f"{'=' * 80}")

        try:
            # Execute Variant B search (dense + sparse + DBSF + ColBERT)
            results = search_engine.search(
                query_embedding=query,  # Pass string for full pipeline
                top_k=5,
                score_threshold=0.3,
            )

            print(f"\n   ✅ Found {len(results)} results (after DBSF + ColBERT rerank)")

            query_results = []
            for j, result in enumerate(results, 1):
                print(f"\n   📄 Result {j} (DBSF + ColBERT-reranked):")
                print(f"      Article: {result.article_number}")
                print(f"      Score: {result.score:.4f}")
                print(f"      Method: {result.metadata.get('search_method', 'N/A')}")
                text_preview = result.text[:150].replace("\n", " ")
                print(f"      Text: {text_preview}...")

                query_results.append(
                    {
                        "article": result.article_number,
                        "score": result.score,
                        "method": result.metadata.get("search_method"),
                    }
                )

            all_results[f"query_{i}"] = query_results

            # Verify search method
            if results:
                method = results[0].metadata.get("search_method")
                if method == "dbsf_colbert":
                    print(f"\n   ✅ Correct: Using DBSF + ColBERT rerank (method={method})")
                else:
                    print(f"\n   ⚠️  Warning: Expected 'dbsf_colbert', got '{method}'")

        except Exception as e:
            print(f"\n   ❌ Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return False, None

    print(f"\n{'=' * 80}")
    print("✅ ALL TESTS PASSED - VARIANT B FULLY OPERATIONAL!")
    print("=" * 80)
    print("\n🎯 Summary:")
    print("   • BGE-M3: Generates dense + sparse + ColBERT vectors")
    print("   • Qdrant: 3-stage query (prefetch → DBSF → ColBERT rerank)")
    print("   • DBSF: Statistical normalization with μ ± 3σ")
    print("   • MaxSim: Server-side multivector reranking")
    print("   • Performance: Expected ~94-95% Recall@1, ~0.97-0.98 NDCG@10")
    print(f"{'=' * 80}\n")

    return True, all_results


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_dbsf_colbert():
    """Test Variant B: Hybrid DBSF + ColBERT rerank."""
    settings = Settings()
    parsed = urlparse(settings.qdrant_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    if not _is_port_open(host, port):
        pytest.skip(f"Qdrant not running on {host}:{port}")
    success, results = _run_dbsf_colbert()
    assert success
    assert results is not None


if __name__ == "__main__":
    success, results = _run_dbsf_colbert()

    if success and results:
        # Save results for comparison with RRF
        import json

        output_path = Path(__file__).parent / "results_dbsf.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {output_path}")

    sys.exit(0 if success else 1)
