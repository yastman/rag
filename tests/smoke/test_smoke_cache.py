# tests/smoke/test_smoke_cache.py
"""Smoke tests for cache operations with live Redis."""

import os
import time

import pytest

from telegram_bot.services.cache import CacheService


@pytest.fixture(scope="module")
async def cache_service():
    """CacheService for testing."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    service = CacheService(redis_url=redis_url)
    await service.initialize()
    yield service
    if service.redis_client:
        keys = await service.redis_client.keys("rag:smoke_test:*")
        if keys:
            await service.redis_client.delete(*keys)
    await service.close()


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
class TestSmokeCache:
    """Test cache operations with live Redis."""

    @pytest.mark.asyncio
    async def test_redis_connection_healthy(self, cache_service):
        """Redis should be reachable."""
        pong = await cache_service.redis_client.ping()
        assert pong is True

    @pytest.mark.asyncio
    async def test_cache_write_and_read(self, cache_service):
        """Basic cache write/read should work."""
        key = f"rag:smoke_test:{int(time.time())}"
        await cache_service.redis_client.setex(key, 60, "test_value")
        result = await cache_service.redis_client.get(key)
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_rerank_cache_roundtrip(self, cache_service):
        """RerankCache should store and retrieve correctly."""
        query_hash = f"smoke_rerank_{int(time.time())}"
        chunk_ids = ["chunk1", "chunk2"]
        results = [{"id": "chunk1", "score": 0.95}]

        await cache_service.store_rerank_results(query_hash, chunk_ids, results)
        cached = await cache_service.get_cached_rerank(query_hash, chunk_ids)

        assert cached is not None
        assert cached[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_cache_metrics_exist(self, cache_service):
        """Cache metrics dict should exist."""
        assert "rerank" in cache_service.metrics
        assert "hits" in cache_service.metrics["rerank"]
