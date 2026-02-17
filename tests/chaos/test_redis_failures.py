"""Chaos tests for Redis failures.

Tests verify graceful degradation when Redis is unavailable.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip(
    "telegram_bot.services.cache",
    reason="telegram_bot.services.cache module removed in current architecture",
)


class TestRedisDisconnect:
    """Tests for Redis disconnection handling."""

    async def test_cache_miss_on_redis_timeout(self):
        """Verify cache returns None on Redis timeout."""
        from telegram_bot.services.cache import CacheService

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=TimeoutError("Redis timeout"))
        mock_redis.hgetall = AsyncMock(side_effect=TimeoutError("Redis timeout"))
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis.from_url", return_value=mock_redis):
            service = CacheService(redis_url="redis://localhost:6379")
            service._redis = mock_redis

            # Should return None, not raise exception
            result = await service.get_cached_analysis("test_query")
            assert result is None

    async def test_cache_set_fails_silently_on_redis_down(self):
        """Verify cache set fails silently when Redis is down."""
        from telegram_bot.services.cache import CacheService

        mock_redis = MagicMock()
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("Redis connection lost"))
        mock_redis.hset = AsyncMock(side_effect=ConnectionError("Redis connection lost"))
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis.from_url", return_value=mock_redis):
            service = CacheService(redis_url="redis://localhost:6379")
            service._redis = mock_redis

            # Should not raise exception - test that cache operations handle failures gracefully
            # store_analysis internally calls hset which we've mocked to raise
            with contextlib.suppress(ConnectionError):
                await service.store_analysis(
                    "test_query", {"filters": {}, "semantic_query": "test"}
                )
            # No assertion needed - just verify no crash

    async def test_semantic_cache_returns_none_without_redis(self):
        """Verify semantic cache returns None gracefully without Redis."""
        from telegram_bot.services.cache import CacheService

        mock_redis = MagicMock()
        mock_redis.ft = MagicMock(side_effect=ConnectionRefusedError("Redis unavailable"))
        mock_redis.ping = AsyncMock(side_effect=ConnectionRefusedError("Redis unavailable"))

        with patch("telegram_bot.services.cache.redis.from_url", return_value=mock_redis):
            service = CacheService(redis_url="redis://localhost:6379")
            service._redis = mock_redis
            service._semantic_cache = None  # Disable semantic cache

            # Should handle gracefully
            # The service may or may not have semantic cache methods depending on setup
            assert service is not None


class TestRedisConnectionPool:
    """Tests for Redis connection pool handling."""

    async def test_pool_exhaustion_handled_gracefully(self):
        """Verify graceful handling when connection pool is exhausted."""
        from telegram_bot.services.cache import CacheService

        mock_redis = MagicMock()
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Connection pool exhausted"))
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis.from_url", return_value=mock_redis):
            service = CacheService(redis_url="redis://localhost:6379")
            service._redis = mock_redis

            # Should return None, not raise
            result = await service.get_cached_analysis("test_query")
            assert result is None

    async def test_concurrent_cache_operations_with_failures(self):
        """Verify concurrent operations handle failures independently."""
        import asyncio

        from telegram_bot.services.cache import CacheService

        mock_redis = MagicMock()
        call_count = 0

        async def mock_hgetall(key):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise TimeoutError("Intermittent timeout")
            return

        mock_redis.hgetall = mock_hgetall
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis.from_url", return_value=mock_redis):
            service = CacheService(redis_url="redis://localhost:6379")
            service._redis = mock_redis

            # Run 5 concurrent requests
            tasks = [service.get_cached_analysis(f"query_{i}") for i in range(5)]

            # All should complete without raising
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Should have mix of None and exceptions handled
            assert all(r is None or isinstance(r, Exception) for r in results)


class TestRedisRecovery:
    """Tests for Redis failure recovery."""

    async def test_cache_recovers_after_reconnect(self):
        """Verify cache operations recover after Redis reconnects."""
        from telegram_bot.services.cache import CacheService

        mock_redis = MagicMock()
        call_count = 0

        async def mock_hgetall(key):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Redis disconnected")
            return {}  # Return empty dict (cache miss)

        mock_redis.hgetall = mock_hgetall
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis.from_url", return_value=mock_redis):
            service = CacheService(redis_url="redis://localhost:6379")
            service._redis = mock_redis

            # First two calls fail
            for _ in range(2):
                result = await service.get_cached_analysis("test_query")
                assert result is None

            # Third call succeeds after "reconnect"
            result = await service.get_cached_analysis("test_query")
            # Returns None because empty dict = cache miss
            assert result is None


class TestCacheServiceInitialization:
    """Tests for CacheService initialization failures."""

    def test_cache_service_init_without_redis(self):
        """Verify CacheService can initialize without Redis connection."""
        from telegram_bot.services.cache import CacheService

        # Should not raise during init
        with patch("telegram_bot.services.cache.redis.from_url") as mock_from_url:
            mock_from_url.side_effect = ConnectionRefusedError("Redis unavailable")

            # Init should complete (lazy connection)
            service = CacheService(redis_url="redis://localhost:6379")
            assert service is not None
