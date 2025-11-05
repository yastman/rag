#!/usr/bin/env python3
"""Test script for 4-tier cache system."""

import asyncio
import os
import sys
import time

import httpx
from dotenv import load_dotenv


# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from telegram_bot.services.cache import CacheService


load_dotenv()


class CacheTester:
    """Test all cache tiers."""

    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.cache = CacheService(redis_url=redis_url)
        self.bge_url = os.getenv("BGE_M3_URL", "http://localhost:8001")
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text."""
        response = await self.http_client.post(
            f"{self.bge_url}/encode/dense", json={"texts": [text]}
        )
        response.raise_for_status()
        data = response.json()
        return data["dense_vecs"][0]

    async def test_redis_connection(self) -> bool:
        """Test 1: Redis connection."""
        print("\n🔧 Test 1: Redis Connection")
        print("-" * 50)
        try:
            await self.cache.initialize()
            print("✅ Redis connected successfully")
            print(
                f"   URL: {self.cache.redis_client.connection_pool.connection_kwargs.get('host')}"
            )
            return True
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False

    async def test_embeddings_cache(self) -> bool:
        """Test 2: Embeddings cache (Tier 1)."""
        print("\n📊 Test 2: Embeddings Cache (Tier 1)")
        print("-" * 50)
        try:
            test_text = "Търся апартамент в София"

            # First request - cache miss
            print("1️⃣ First request (expect MISS)...")
            start = time.time()
            cached = await self.cache.get_cached_embedding(test_text)
            assert cached is None, "Expected cache miss"
            print("   ✅ Cache MISS (correct)")

            # Generate and store
            print("2️⃣ Generating embedding...")
            embedding = await self.generate_embedding(test_text)
            duration = time.time() - start
            print(f"   ✅ Generated {len(embedding)}-dim embedding ({duration:.2f}s)")

            print("3️⃣ Storing in cache...")
            await self.cache.store_embedding(test_text, embedding)
            print("   ✅ Stored successfully")

            # Second request - cache hit
            print("4️⃣ Second request (expect HIT)...")
            start = time.time()
            cached = await self.cache.get_cached_embedding(test_text)
            duration = time.time() - start
            assert cached is not None, "Expected cache hit"
            assert len(cached) == len(embedding), "Embedding size mismatch"
            print(f"   ✅ Cache HIT ({duration:.4f}s - much faster!)")

            return True
        except Exception as e:
            print(f"❌ Embeddings cache test failed: {e}")
            return False

    async def test_semantic_cache(self) -> bool:
        """Test 3: Semantic cache for LLM answers (Tier 1)."""
        print("\n🧠 Test 3: Semantic Cache (Tier 1)")
        print("-" * 50)
        try:
            query1 = "Какви апартаменти има в Пловдив?"
            query2 = "Покажи ми жилища в град Пловдив"  # Похожий запрос
            answer = "В Пловдив има 5 апартамента: 2-стаен на ул. Цариградско шосе..."

            # Store first query-answer
            print("1️⃣ Storing first query-answer pair...")
            emb1 = await self.generate_embedding(query1)
            await self.cache.store_semantic_cache(query1, emb1, answer)
            print(f"   ✅ Stored: '{query1[:30]}...'")

            # Check exact match
            print("2️⃣ Checking same query (exact match)...")
            cached = await self.cache.check_semantic_cache(emb1)
            assert cached is not None, "Expected semantic cache hit"
            print("   ✅ Found exact match")

            # Check similar query
            print("3️⃣ Checking similar query (semantic match)...")
            emb2 = await self.generate_embedding(query2)
            cached = await self.cache.check_semantic_cache(emb2)
            if cached is not None:
                print("   ✅ Found semantic match (threshold >= 0.85)")
                print(f"   📝 Query: '{query2[:30]}...'")
                print(f"   📝 Answer: '{cached[:50]}...'")
            else:
                print("   ⚠️ No semantic match (similarity < 0.85)")

            return True
        except Exception as e:
            print(f"❌ Semantic cache test failed: {e}")
            return False

    async def test_analyzer_cache(self) -> bool:
        """Test 4: QueryAnalyzer cache (Tier 2)."""
        print("\n🔍 Test 4: QueryAnalyzer Cache (Tier 2)")
        print("-" * 50)
        try:
            query = "Апартамент в София до 150000 лева"
            analysis = {
                "filters": {"city": "София", "price_max": 150000},
                "semantic_query": "апартамент",
            }

            # Store analysis
            print("1️⃣ Storing analysis...")
            await self.cache.store_analysis(query, analysis)
            print(f"   ✅ Stored filters: {analysis['filters']}")

            # Retrieve - cache hit
            print("2️⃣ Retrieving analysis (expect HIT)...")
            start = time.time()
            cached = await self.cache.get_cached_analysis(query)
            duration = time.time() - start
            assert cached is not None, "Expected cache hit"
            assert cached["filters"] == analysis["filters"], "Filters mismatch"
            print(f"   ✅ Cache HIT ({duration:.4f}s)")
            print(f"   📋 Filters: {cached['filters']}")

            # Different query - cache miss
            print("3️⃣ Different query (expect MISS)...")
            cached = await self.cache.get_cached_analysis("Друг апартамент")
            assert cached is None, "Expected cache miss"
            print("   ✅ Cache MISS (correct)")

            return True
        except Exception as e:
            print(f"❌ Analyzer cache test failed: {e}")
            return False

    async def test_search_cache(self) -> bool:
        """Test 5: Qdrant search results cache (Tier 2)."""
        print("\n🔎 Test 5: Search Results Cache (Tier 2)")
        print("-" * 50)
        try:
            # Test embedding
            embedding = [0.1] * 1024  # Dummy 1024-dim vector
            filters = {"city": "София"}
            results = [
                {"id": "apt1", "score": 0.95, "metadata": {"city": "София"}},
                {"id": "apt2", "score": 0.87, "metadata": {"city": "София"}},
            ]

            # Store results
            print("1️⃣ Storing search results...")
            await self.cache.store_search_results(embedding, filters, results)
            print(f"   ✅ Stored {len(results)} results with filters: {filters}")

            # Retrieve - cache hit
            print("2️⃣ Retrieving results (expect HIT)...")
            start = time.time()
            cached = await self.cache.get_cached_search(embedding, filters)
            duration = time.time() - start
            assert cached is not None, "Expected cache hit"
            assert len(cached) == len(results), "Results count mismatch"
            print(f"   ✅ Cache HIT ({duration:.4f}s)")
            print(f"   📋 Found {len(cached)} results")

            # Different filters - cache miss
            print("3️⃣ Different filters (expect MISS)...")
            cached = await self.cache.get_cached_search(embedding, {"city": "Пловдив"})
            assert cached is None, "Expected cache miss"
            print("   ✅ Cache MISS (correct)")

            return True
        except Exception as e:
            print(f"❌ Search cache test failed: {e}")
            return False

    async def test_metrics(self) -> bool:
        """Test 6: Cache metrics."""
        print("\n📈 Test 6: Cache Metrics")
        print("-" * 50)
        try:
            metrics = self.cache.get_metrics()
            print(f"Overall hit rate: {metrics['overall_hit_rate']:.1%}")
            print(f"Total requests: {metrics['total_requests']}")
            print(f"Total hits: {metrics['total_hits']}")
            print(f"Total misses: {metrics['total_misses']}")
            print("\nBy cache type:")
            for cache_type, stats in metrics["by_type"].items():
                print(
                    f"  {cache_type:12s}: {stats['hit_rate']:>6.1%} ({stats['hits']}/{stats['requests']} hits)"
                )
            return True
        except Exception as e:
            print(f"❌ Metrics test failed: {e}")
            return False

    async def run_all_tests(self):
        """Run all cache tests."""
        print("=" * 50)
        print("🧪 Redis Cache Tests - 4-Tier Architecture")
        print("=" * 50)

        results = []

        # Test 1: Redis connection
        results.append(await self.test_redis_connection())

        if not results[0]:
            print("\n❌ Redis connection failed - skipping other tests")
            return False

        # Test 2: Embeddings cache
        results.append(await self.test_embeddings_cache())

        # Test 3: Semantic cache
        results.append(await self.test_semantic_cache())

        # Test 4: Analyzer cache
        results.append(await self.test_analyzer_cache())

        # Test 5: Search cache
        results.append(await self.test_search_cache())

        # Test 6: Metrics
        results.append(await self.test_metrics())

        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        passed = sum(results)
        total = len(results)
        print(f"Passed: {passed}/{total}")
        if passed == total:
            print("✅ All tests passed!")
        else:
            print(f"❌ {total - passed} test(s) failed")
        print("=" * 50)

        await self.http_client.aclose()
        return passed == total


async def main():
    """Main entry point."""
    tester = CacheTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
