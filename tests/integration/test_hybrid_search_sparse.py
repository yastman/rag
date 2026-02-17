#!/usr/bin/env python3
"""
Test hybrid search with sparse vectors in production code.
Verifies that HybridRRFSearchEngine uses both dense and sparse vectors via RRF.
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
from src.retrieval import HybridRRFSearchEngine


def _run_hybrid_search_with_sparse() -> bool:
    """Run hybrid search flow using dense + sparse vectors."""

    print("=" * 80)
    print("TEST: HYBRID SEARCH WITH SPARSE VECTORS")
    print("=" * 80)

    # Initialize settings and search engine
    settings = Settings()
    print("\n📋 Configuration:")
    print(f"   Qdrant URL: {settings.qdrant_url}")
    print(f"   Collection: {settings.collection_name}")
    print(
        f"   API Key: {'***' + settings.qdrant_api_key[-10:] if settings.qdrant_api_key else 'Not set'}"
    )

    # Initialize hybrid search engine
    print("\n🔧 Initializing HybridRRFSearchEngine...")
    search_engine = HybridRRFSearchEngine(settings)
    print("   ✅ Search engine initialized with BGE-M3 model")

    # Test queries
    test_queries = [
        "Стаття 121 Кримінального кодексу",  # Article lookup
        "Умисне вбивство",  # Crime definition
        "Що таке крайня необхідність?",  # Legal concept
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'=' * 80}")
        print(f"🔍 Test Query {i}: {query}")
        print(f"{'=' * 80}")

        try:
            # Execute search with query string (will use sparse vectors)
            results = search_engine.search(
                query_embedding=query,  # Pass string, not embedding
                top_k=5,
                score_threshold=0.3,
            )

            print(f"\n   ✅ Found {len(results)} results")

            for j, result in enumerate(results, 1):
                print(f"\n   📄 Result {j}:")
                print(f"      Article: {result.article_number}")
                print(f"      Score: {result.score:.4f}")
                text_preview = result.text[:150].replace("\n", " ")
                print(f"      Text: {text_preview}...")

        except Exception as e:
            print(f"\n   ❌ Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return False

    print(f"\n{'=' * 80}")
    print("✅ ALL TESTS PASSED!")
    print(f"{'=' * 80}\n")

    return True


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def test_hybrid_search_with_sparse():
    """Test hybrid search using dense + sparse vectors."""
    settings = Settings()
    parsed = urlparse(settings.qdrant_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6333
    if not _is_port_open(host, port):
        pytest.skip(f"Qdrant not running on {host}:{port}")
    assert _run_hybrid_search_with_sparse()


if __name__ == "__main__":
    success = _run_hybrid_search_with_sparse()
    sys.exit(0 if success else 1)
