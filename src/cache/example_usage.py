#!/usr/bin/env python3
"""
Example: How to use Redis semantic cache in RAG pipeline.

This example shows integration with Qdrant search engine.
Run from Docker container or ensure Redis is accessible at 'redis:6379'.
"""

import asyncio
import os

from cache.redis_semantic_cache import RedisSemanticCache


async def example_cached_rag_query():
    """Example: RAG query with semantic caching."""

    # Initialize cache
    cache = RedisSemanticCache(
        index_version="1.0.0",  # Match your Qdrant collection version
        embedding_ttl_days=30,  # Cache embeddings for 30 days
        response_ttl_minutes=30,  # Cache responses for 30 minutes
    )

    print("🔄 Example: Cached RAG Query")
    print("=" * 60)

    test_query = "Стаття 121 Кримінального кодексу України"

    # Step 1: Try to get cached response (fastest)
    print(f"\n1️⃣  Checking response cache for: '{test_query}'")
    cached_response = await cache.get_response(test_query, top_k=10)

    if cached_response:
        print("   ✅ Cache HIT! Returning cached response.")
        print("   ⚡ Latency saved: ~200ms")
        return cached_response

    print("   ❌ Cache MISS. Proceeding to embedding cache...")

    # Step 2: Try to get cached embedding
    print("\n2️⃣  Checking embedding cache...")
    query_embedding = await cache.get_embedding(test_query)

    if query_embedding:
        print("   ✅ Cache HIT! Using cached embedding.")
        print("   ⚡ Latency saved: ~10ms + $0.00001")
    else:
        print("   ❌ Cache MISS. Generating new embedding...")

        # In real code, call BGE-M3:
        # query_embedding = await bge_m3_client.embed(test_query)

        # For example, use dummy embedding
        query_embedding = [0.1] * 1024

        # Cache it for future use
        await cache.set_embedding(test_query, query_embedding)
        print("   ✅ Embedding cached for 30 days")

    # Step 3: Search Qdrant (real search would go here)
    print("\n3️⃣  Searching Qdrant...")

    # In real code:
    # results = await qdrant_client.search(
    #     collection_name="contextual_rag_criminal_code_v1",
    #     query_vector=query_embedding,
    #     limit=10
    # )

    # For example, use dummy results
    results = [
        {
            "id": "article_121",
            "text": "Стаття 121. Умисне тяжке тілесне ушкодження",
            "score": 0.95,
        },
        {
            "id": "article_120",
            "text": "Стаття 120. Доведення до самогубства",
            "score": 0.85,
        },
    ]

    print(f"   ✅ Found {len(results)} results")

    # Step 4: Cache the full response
    response = {"query": test_query, "results": results, "top_k": 10}

    await cache.set_response(test_query, top_k=10, response=response)
    print("\n4️⃣  Response cached for 30 minutes")

    # Step 5: Show cache stats
    stats = cache.get_stats()
    print("\n📊 Cache Statistics:")
    print(f"   Hits: {stats['cache_hits']}")
    print(f"   Misses: {stats['cache_misses']}")
    print(f"   Hit rate: {stats['hit_rate']:.1%}")
    print(f"   Cost saved: ${stats['saved_cost_usd']:.6f}")

    await cache.redis.close()

    return response


async def example_cache_benefits():
    """Show performance benefits of caching."""

    print("\n" + "=" * 60)
    print("📊 Cache Performance Benefits")
    print("=" * 60)

    cache = RedisSemanticCache(index_version="1.0.0")

    test_query = "Що таке шахрайство за українським правом?"

    # First query (cold - no cache)
    print("\n🥶 COLD query (no cache):")
    print("   1. Generate embedding: 10ms + $0.00001")
    print("   2. Search Qdrant: 200ms")
    print("   3. Total: 210ms")

    # Simulate first query
    embedding = [0.2] * 1024
    await cache.set_embedding(test_query, embedding)
    response = {"query": test_query, "results": []}
    await cache.set_response(test_query, top_k=10, response=response)

    # Second query (warm - embedding cached)
    print("\n🌡️  WARM query (embedding cached):")
    print("   1. Get embedding from cache: 2ms + $0")
    print("   2. Search Qdrant: 200ms")
    print("   3. Total: 202ms (4% faster)")

    # Third query (hot - full response cached)
    print("\n🔥 HOT query (response cached):")
    print("   1. Get response from cache: 2ms + $0")
    print("   2. Total: 2ms (100x faster!)")

    # Calculate savings
    print("\n💰 Cost Savings (1000 queries/day):")
    print("   Without cache: $10.00/day (1000 × $0.01)")
    print("   With cache (70% hit): $3.00/day (300 × $0.01)")
    print("   Monthly savings: $210/month")

    await cache.redis.close()


async def example_version_invalidation():
    """Show how version-based cache invalidation works."""

    print("\n" + "=" * 60)
    print("🔄 Version-Based Cache Invalidation")
    print("=" * 60)

    test_query = "Стаття 115 УК"

    # Version 1.0.0
    print("\n📌 Index version 1.0.0:")
    cache_v1 = RedisSemanticCache(index_version="1.0.0")
    await cache_v1.set_embedding(test_query, [0.1] * 1024)
    print("   ✅ Embedding cached with key: embedding_v1.0.0_...")

    # Check cache
    cached = await cache_v1.get_embedding(test_query)
    print(f"   ✅ Cache hit: {cached is not None}")

    # Rebuild index → Version 1.0.1
    print("\n🔨 Index rebuilt → Version 1.0.1")
    cache_v2 = RedisSemanticCache(index_version="1.0.1")

    # Check cache (should miss)
    cached = await cache_v2.get_embedding(test_query)
    print(f"   ❌ Cache miss: {cached is None} (key changed to embedding_v1.0.1_...)")
    print("   ✅ Old cache automatically invalidated!")

    await cache_v1.redis.close()
    await cache_v2.redis.close()


def main():
    """Run all examples."""
    print("=" * 60)
    print("Redis Semantic Cache - Usage Examples")
    print("=" * 60)
    print("\n⚠️  Note: These examples require Redis at 'redis:6379'")
    print("   Run from Docker container or adjust REDIS_HOST env var.")
    print()

    # Check if we can connect (rough check)
    redis_host = os.getenv("REDIS_HOST", "redis")
    if redis_host == "redis":
        print("💡 Tip: Set REDIS_HOST=localhost if running outside Docker")

    try:
        asyncio.run(example_cached_rag_query())
        asyncio.run(example_cache_benefits())
        asyncio.run(example_version_invalidation())

        print("\n" + "=" * 60)
        print("✅ All examples completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  - Ensure Redis is running: docker ps | grep redis")
        print("  - Check REDIS_PASSWORD env var is set")
        print("  - If outside Docker, set REDIS_HOST=localhost")


if __name__ == "__main__":
    main()
