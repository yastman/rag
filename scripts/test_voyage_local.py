#!/usr/bin/env python3
"""Manual test for Voyage services against live APIs."""

import asyncio
import os
import sys

# Ensure env is loaded
from dotenv import load_dotenv


load_dotenv()


async def test_embedding():
    """Test VoyageEmbeddingService with real API."""
    from telegram_bot.services import VoyageEmbeddingService

    print("Testing VoyageEmbeddingService...")
    svc = VoyageEmbeddingService()

    query = "квартира в Солнечном береге"
    embedding = await svc.embed_query(query)

    print(f"  Query: {query}")
    print(f"  Embedding dimension: {len(embedding)}")
    print(f"  First 5 values: {embedding[:5]}")

    assert len(embedding) == 1024, f"Expected 1024-dim, got {len(embedding)}"
    print("  ✓ Embedding test PASSED")
    return embedding


async def test_search(query_vector: list[float]):
    """Test RetrieverService with real Qdrant."""
    from telegram_bot.services import RetrieverService

    print("\nTesting RetrieverService...")
    retriever = RetrieverService(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY", ""),
        collection_name=os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage"),
    )

    results = retriever.search(query_vector=query_vector, top_k=10, min_score=0.3)

    print(f"  Results: {len(results)} documents")
    for i, r in enumerate(results[:3], 1):
        print(f"  {i}. Score: {r['score']:.4f} - {r['metadata'].get('topic', 'N/A')[:50]}")

    assert len(results) > 0, "Expected at least 1 result"
    print("  ✓ Search test PASSED")
    return results


async def test_rerank(query: str, results: list):
    """Test VoyageRerankerService with real API."""
    from telegram_bot.services import VoyageRerankerService

    print("\nTesting VoyageRerankerService...")
    reranker = VoyageRerankerService()

    reranked = await reranker.rerank(query=query, documents=results, top_k=5)

    print(f"  Reranked: {len(reranked)} documents")
    for i, r in enumerate(reranked[:3], 1):
        print(f"  {i}. Rerank: {r['rerank_score']:.4f}, Original: {r['original_score']:.4f}")

    assert len(reranked) > 0, "Expected reranked results"
    print("  ✓ Rerank test PASSED")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Voyage AI Local Integration Tests")
    print("=" * 60)

    query = "квартира в Солнечном береге"

    try:
        embedding = await test_embedding()
        results = await test_search(embedding)
        await test_rerank(query, results)

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
