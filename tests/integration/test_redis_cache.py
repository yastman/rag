#!/usr/bin/env python3
"""Test Redis semantic cache connectivity and basic operations.

Legacy integration test — requires live Redis. Run manually:
    python tests/integration/test_redis_cache.py

Excluded from CI via @pytest.mark.legacy_api marker.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest


def _check_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (OSError, TimeoutError):
            return False


# Mark entire module as legacy (skipped in CI: -m "not legacy_api")
# Also skip if Redis hostname (default: "redis") is not reachable
pytestmark = [
    pytest.mark.legacy_api,
    pytest.mark.skipif(
        not _check_tcp(os.getenv("REDIS_HOST", "redis"), 6379),
        reason=f"Redis not reachable at {os.getenv('REDIS_HOST', 'redis')}:6379",
    ),
]

# Add src to path for legacy import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cache.redis_semantic_cache import RedisSemanticCache


async def test_redis_connection():
    """Test basic Redis connectivity."""
    print("🔄 Testing Redis cache connection...")

    try:
        # Initialize cache (uses env REDIS_PASSWORD automatically)
        cache = RedisSemanticCache(index_version="1.0.0")

        # Test ping
        await cache.redis.ping()
        print("✅ Redis connection: OK")

        # Test embedding cache
        test_query = "Стаття 121 Кримінального кодексу України"
        test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Set embedding
        await cache.set_embedding(test_query, test_embedding)
        print("✅ Set embedding: OK")

        # Get embedding
        cached_embedding = await cache.get_embedding(test_query)
        assert cached_embedding == test_embedding, "Embedding mismatch!"
        print("✅ Get embedding: OK")

        # Test response cache
        test_response = {
            "query": test_query,
            "results": [
                {"text": "Стаття 121. Умисне тяжке тілесне ушкодження", "score": 0.95},
                {"text": "Стаття 120. Доведення до самогубства", "score": 0.85},
            ],
        }

        # Set response
        await cache.set_response(test_query, top_k=10, response=test_response)
        print("✅ Set response: OK")

        # Get response
        cached_response = await cache.get_response(test_query, top_k=10)
        assert cached_response is not None, "Response not found!"
        assert cached_response["query"] == test_query, "Query mismatch!"
        print("✅ Get response: OK")

        # Check stats
        stats = cache.get_stats()
        print("\n📊 Cache stats:")
        print(f"   Hits: {stats['cache_hits']}")
        print(f"   Misses: {stats['cache_misses']}")
        print(f"   Hit rate: {stats['hit_rate']:.1%}")
        print(f"   Cost saved: ${stats['saved_cost_usd']:.6f}")
        print(f"   Index version: {stats['index_version']}")

        # Cleanup
        await cache.redis.close()
        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


async def test_cache_invalidation():
    """Test version-based cache invalidation."""
    print("\n🔄 Testing cache invalidation...")

    try:
        test_query = "Стаття 115 УК"
        test_embedding = [0.5, 0.6, 0.7]

        # Version 1.0.0
        cache_v1 = RedisSemanticCache(index_version="1.0.0")
        await cache_v1.set_embedding(test_query, test_embedding)

        cached_v1 = await cache_v1.get_embedding(test_query)
        assert cached_v1 == test_embedding, "V1 embedding not found!"
        print("✅ Version 1.0.0 cache: OK")

        # Version 1.0.1 (different cache keys)
        cache_v2 = RedisSemanticCache(index_version="1.0.1")
        cached_v2 = await cache_v2.get_embedding(test_query)
        assert cached_v2 is None, "V2 should not find V1 cache!"
        print("✅ Version 1.0.1 cache: Correctly invalidated")

        # Cleanup
        await cache_v1.redis.close()
        await cache_v2.redis.close()
        print("✅ Cache invalidation test passed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Run all tests."""
    print("=" * 60)
    print("Redis Semantic Cache - Connection Test")
    print("=" * 60)

    # Check environment
    redis_password = os.getenv("REDIS_PASSWORD")
    if not redis_password:
        print("⚠️  Warning: REDIS_PASSWORD not set in environment")
        print("   Loading from /home/admin/.env...")

        # Try to load from .env
        env_file = Path("/home/admin/.env")
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("REDIS_PASSWORD="):
                        redis_password = line.split("=", 1)[1].strip()
                        os.environ["REDIS_PASSWORD"] = redis_password
                        print("✅ Loaded REDIS_PASSWORD from .env")
                        break

    if not redis_password:
        print("❌ REDIS_PASSWORD not found!")
        print("\nPlease set REDIS_PASSWORD environment variable:")
        print("  export REDIS_PASSWORD='your_password'")
        sys.exit(1)

    print("\n📋 Configuration:")
    print(f"   REDIS_HOST: {os.getenv('REDIS_HOST', 'redis')}")
    print(f"   REDIS_PORT: {os.getenv('REDIS_PORT', '6379')}")
    print(f"   REDIS_DB: {os.getenv('REDIS_CACHE_DB', '2')}")
    print(f"   REDIS_PASSWORD: {'*' * 8} (hidden)")
    print()

    # Run tests
    asyncio.run(test_redis_connection())
    asyncio.run(test_cache_invalidation())

    print("\n" + "=" * 60)
    print("🎉 All tests passed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
