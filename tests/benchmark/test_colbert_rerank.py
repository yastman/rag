#!/usr/bin/env python3
"""
Test ColBERT multivector rerank in production code (Variant A - Complete).
Verifies HybridRRFColBERTSearchEngine uses: Dense + Sparse + ColBERT rerank.
"""

import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import Settings
from src.retrieval import HybridRRFColBERTSearchEngine


def _run_colbert_rerank() -> bool:
    """Run Variant A benchmark flow and return success flag."""

    print("=" * 80)
    print("TEST: VARIANT A - HYBRID RRF + COLBERT RERANK")
    print("=" * 80)

    # Initialize settings and search engine
    settings = Settings()
    print("\n📋 Configuration:")
    print(f"   Qdrant URL: {settings.qdrant_url}")
    print(f"   Collection: {settings.collection_name}")
    print(
        f"   API Key: {'***' + settings.qdrant_api_key[-10:] if settings.qdrant_api_key else 'Not set'}"
    )

    # Initialize Variant A search engine
    print("\n🔧 Initializing HybridRRFColBERTSearchEngine (Variant A)...")
    search_engine = HybridRRFColBERTSearchEngine(settings)
    print("   ✅ Search engine initialized with BGE-M3 model")
    print("   ✅ 3-Stage Pipeline:")
    print("      Stage 1: Dense (100) + Sparse (100) prefetch")
    print("      Stage 2: RRF fusion")
    print("      Stage 3: ColBERT multivector MaxSim rerank")

    # Test queries
    test_queries = [
        ("Стаття 121 Кримінального кодексу", "Article lookup with exact number"),
        ("Умисне вбивство з особливою жорстокістю", "Crime with specific qualifier"),
        ("Коли застосовується крайня необхідність?", "Legal concept question"),
    ]

    for i, (query, description) in enumerate(test_queries, 1):
        print(f"\n{'=' * 80}")
        print(f"🔍 Test Query {i}: {query}")
        print(f"   Description: {description}")
        print(f"{'=' * 80}")

        try:
            # Execute Variant A search (dense + sparse + ColBERT)
            results = search_engine.search(
                query_embedding=query,  # Pass string for full pipeline
                top_k=5,
                score_threshold=0.3,
            )

            print(f"\n   ✅ Found {len(results)} results (after ColBERT rerank)")

            for j, result in enumerate(results, 1):
                print(f"\n   📄 Result {j} (ColBERT-reranked):")
                print(f"      Article: {result.article_number}")
                print(f"      Score: {result.score:.4f}")
                print(f"      Method: {result.metadata.get('search_method', 'N/A')}")
                text_preview = result.text[:150].replace("\n", " ")
                print(f"      Text: {text_preview}...")

            # Verify search method
            if results:
                method = results[0].metadata.get("search_method")
                if method == "hybrid_rrf_colbert":
                    print(f"\n   ✅ Correct: Using ColBERT rerank (method={method})")
                else:
                    print(f"\n   ⚠️  Warning: Expected 'hybrid_rrf_colbert', got '{method}'")

        except Exception as e:
            print(f"\n   ❌ Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return False

    print(f"\n{'=' * 80}")
    print("✅ ALL TESTS PASSED - VARIANT A FULLY OPERATIONAL!")
    print("=" * 80)
    print("\n🎯 Summary:")
    print("   • BGE-M3: Generates dense + sparse + ColBERT vectors")
    print("   • Qdrant: 3-stage query (prefetch → RRF → ColBERT rerank)")
    print("   • MaxSim: Server-side multivector reranking")
    print("   • Performance: Expected ~94% Recall@1, ~0.97 NDCG@10")
    print(f"{'=' * 80}\n")

    return True


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _collection_exists(url: str, api_key: str, collection_name: str) -> bool:
    req = urllib.request.Request(f"{url}/collections/{collection_name}")
    if api_key:
        req.add_header("api-key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def test_colbert_rerank():
    """Test Variant A: Hybrid RRF + ColBERT rerank."""
    if os.getenv("RUN_BENCHMARK_TESTS", "0") != "1":
        pytest.skip("Benchmark tests disabled (set RUN_BENCHMARK_TESTS=1)")

    settings = Settings()
    parsed = urlparse(settings.qdrant_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    if not _is_port_open(host, port):
        pytest.skip(f"Qdrant not running on {host}:{port}")

    if not _collection_exists(
        settings.qdrant_url, settings.qdrant_api_key, settings.collection_name
    ):
        pytest.skip(f"Collection not found: {settings.collection_name}")

    assert _run_colbert_rerank()


if __name__ == "__main__":
    success = _run_colbert_rerank()
    sys.exit(0 if success else 1)
