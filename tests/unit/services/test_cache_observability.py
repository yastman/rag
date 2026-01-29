# tests/unit/services/test_cache_observability.py
"""Unit tests for CacheService enhanced Langfuse spans."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCacheServiceSpanMetadata:
    """Tests for CacheService span layer attributes."""

    @pytest.fixture
    def cache_service(self):
        """Create CacheService with mocked dependencies."""
        from telegram_bot.services.cache import CacheService

        service = CacheService.__new__(CacheService)
        service.redis_client = MagicMock()
        service.semantic_cache = MagicMock()
        service.distance_threshold = 0.20
        service.metrics = {
            "semantic": {"hits": 0, "misses": 0},
            "search": {"hits": 0, "misses": 0},
            "rerank": {"hits": 0, "misses": 0},
        }
        return service

    @pytest.mark.asyncio
    async def test_check_semantic_cache_includes_layer(self, cache_service):
        """check_semantic_cache should include layer=semantic in span."""
        cache_service.semantic_cache.acheck = AsyncMock(return_value=None)

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await cache_service.check_semantic_cache("test query")

            mock_langfuse.update_current_span.assert_called_once()
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["layer"] == "semantic"
            assert call_kwargs["output"]["hit"] is False

    @pytest.mark.asyncio
    async def test_check_semantic_cache_hit_includes_distance(self, cache_service):
        """Semantic cache hit should include distance in span."""
        cache_service.semantic_cache.acheck = AsyncMock(
            return_value=[{"response": "cached", "vector_distance": 0.05}]
        )

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            result = await cache_service.check_semantic_cache("test query")

            assert result == "cached"
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["hit"] is True
            assert call_kwargs["output"]["distance"] == 0.05

    @pytest.mark.asyncio
    async def test_get_cached_search_includes_layer(self, cache_service):
        """get_cached_search should include layer=retrieval in span."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await cache_service.get_cached_search([0.1] * 10, None)

            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["layer"] == "retrieval"

    @pytest.mark.asyncio
    async def test_get_cached_rerank_includes_layer(self, cache_service):
        """get_cached_rerank should include layer=rerank in span."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await cache_service.get_cached_rerank("query_hash", ["doc1"])

            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["layer"] == "rerank"
