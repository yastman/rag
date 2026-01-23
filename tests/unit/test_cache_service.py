"""Tests for CacheService including RerankCache."""

from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.cache import CacheService


class TestRerankCache:
    """Test RerankCache methods."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_rerank_hit(self, cache_service):
        cache_service.redis_client.get = AsyncMock(return_value='[{"id": "1", "score": 0.9}]')

        result = await cache_service.get_cached_rerank(
            query_hash="abc123",
            chunk_ids=["chunk1", "chunk2"],
        )

        assert result == [{"id": "1", "score": 0.9}]
        assert cache_service.metrics["rerank"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_rerank_miss(self, cache_service):
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_cached_rerank(
            query_hash="abc123",
            chunk_ids=["chunk1"],
        )

        assert result is None
        assert cache_service.metrics["rerank"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_rerank_results(self, cache_service):
        cache_service.redis_client.setex = AsyncMock()

        await cache_service.store_rerank_results(
            query_hash="abc123",
            chunk_ids=["chunk1"],
            results=[{"id": "1", "score": 0.9}],
        )

        cache_service.redis_client.setex.assert_called_once()
        assert cache_service.redis_client.setex.call_args[0][1] == 7200
