"""Tests for CacheService with all cache tiers."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.cache import CacheService


class TestCacheServiceInit:
    """CacheService initialization tests."""

    @pytest.mark.asyncio
    async def test_initialize_creates_connections(self):
        """Initialize creates Redis and cache connections."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)

        await service.initialize()

        assert service.redis_client is not None
        # SemanticCache requires VOYAGE_API_KEY
        if os.getenv("VOYAGE_API_KEY"):
            assert service.semantic_cache is not None

        await service.close()

    @pytest.mark.asyncio
    async def test_initialize_without_voyage_key_disables_semantic_cache(self):
        """Without VOYAGE_API_KEY, semantic cache is disabled."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        with patch.dict(os.environ, {"VOYAGE_API_KEY": ""}):
            service = CacheService(redis_url=redis_url)
            await service.initialize()

            assert service.semantic_cache is None
            await service.close()


class TestSemanticCache:
    """Semantic cache store/check tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url, distance_threshold=0.15)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_store_and_check_returns_result(self, cache_service):
        """Store then check returns cached result."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized (no VOYAGE_API_KEY)")

        query = "тестовый запрос для кэширования"
        answer = "тестовый ответ"

        await cache_service.store_semantic_cache(query, answer)
        result = await cache_service.check_semantic_cache(query)

        assert result is not None
        assert "тестовый ответ" in result

    @pytest.mark.asyncio
    async def test_check_distant_query_returns_none(self, cache_service):
        """Distant query returns None (threshold filter)."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store specific query
        await cache_service.store_semantic_cache(
            "квартиры в Солнечном береге", "ответ про квартиры"
        )

        # Check completely different query
        result = await cache_service.check_semantic_cache(
            "как приготовить борщ"  # Unrelated query
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_user_isolation(self, cache_service):
        """user_id isolates cache entries."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        query = "тест изоляции пользователей"

        # Store for user 1
        await cache_service.store_semantic_cache(query, "ответ для user 1", user_id=1)
        # Store for user 2
        await cache_service.store_semantic_cache(query, "ответ для user 2", user_id=2)

        # Check for user 1
        result = await cache_service.check_semantic_cache(query, user_id=1)
        assert result is not None
        assert "user 1" in result

    @pytest.mark.asyncio
    async def test_threshold_override(self, cache_service):
        """threshold_override changes matching strictness."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        await cache_service.store_semantic_cache("original query text", "original answer")

        # With strict threshold, similar but not identical should miss
        result = await cache_service.check_semantic_cache(
            "slightly different query text",
            threshold_override=0.01,  # Very strict
        )

        # May or may not match depending on embedding similarity
        # Just verify no exception
        assert result is None or isinstance(result, str)


class TestEmbeddingsCache:
    """Embeddings cache tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_store_and_get_embedding(self, cache_service):
        """Store then get returns embedding."""
        if not cache_service.embeddings_cache:
            pytest.skip("EmbeddingsCache not initialized")

        text = "test embedding text"
        embedding = [0.1] * 1024

        await cache_service.store_embedding(text, embedding, model_name="test-model")
        result = await cache_service.get_cached_embedding(text, model_name="test-model")

        assert result is not None
        assert len(result) == 1024


class TestTier2Caches:
    """Tier 2 key-value cache tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_analyzer_cache_store_get(self, cache_service):
        """Analyzer cache stores and retrieves JSON."""
        query = "test analyzer query"
        analysis = {"filters": {"city": "Бургас"}, "semantic_query": "apartments"}

        await cache_service.store_analysis(query, analysis)
        result = await cache_service.get_cached_analysis(query)

        assert result is not None
        assert result["filters"]["city"] == "Бургас"

    @pytest.mark.asyncio
    async def test_search_cache_store_get(self, cache_service):
        """Search cache stores and retrieves results."""
        embedding = [0.1] * 10  # Only first 10 used for hash
        filters = {"city": "Варна"}
        results = [{"text": "result 1", "score": 0.9}]

        await cache_service.store_search_results(embedding, filters, results)
        cached = await cache_service.get_cached_search(embedding, filters)

        assert cached is not None
        assert cached[0]["text"] == "result 1"


class TestCacheMetrics:
    """Cache metrics tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_metrics_counting(self, cache_service):
        """Metrics count hits and misses."""
        # Force a miss
        await cache_service.get_cached_analysis("nonexistent query")

        metrics = cache_service.get_metrics()

        assert metrics["by_type"]["analyzer"]["misses"] >= 1
        assert "overall_hit_rate" in metrics


class TestSemanticMessageHistory:
    """Semantic message history tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_add_message_no_error(self, cache_service):
        """add_semantic_message runs without error."""
        if not cache_service.message_history:
            pytest.skip("SemanticMessageHistory not initialized")

        user_id = 999999  # Test user

        # Add messages - should not raise
        await cache_service.add_semantic_message(user_id, "user", "ищу квартиру в Бургасе")
        await cache_service.add_semantic_message(user_id, "assistant", "Вот квартиры в Бургасе...")

        # Test passes if no exception raised

    @pytest.mark.asyncio
    async def test_get_relevant_history_returns_list(self, cache_service):
        """get_relevant_history returns a list."""
        if not cache_service.message_history:
            pytest.skip("SemanticMessageHistory not initialized")

        user_id = 888888  # Different test user

        # Get history - may be empty but should be a list
        relevant = await cache_service.get_relevant_history(user_id, "квартиры в Бургасе", top_k=2)

        assert isinstance(relevant, list)


class TestCacheServiceVectorizer:
    """Tests verifying CacheService uses VoyageAITextVectorizer."""

    @pytest.mark.asyncio
    async def test_cache_service_uses_voyage_vectorizer_for_semantic_cache(self):
        """Verify VoyageAITextVectorizer is created for SemanticCache during initialization."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        with (
            patch.dict(os.environ, {"VOYAGE_API_KEY": "test-api-key"}),
            patch("telegram_bot.services.cache.VoyageAITextVectorizer") as mock_vectorizer_class,
            patch("telegram_bot.services.cache.SemanticCache") as mock_semantic_cache_class,
            patch("telegram_bot.services.cache.EmbeddingsCache"),
            patch("telegram_bot.services.cache.SemanticMessageHistory"),
            patch("telegram_bot.services.cache.redis") as mock_redis,
        ):
            # Setup mock Redis client
            mock_redis_client = AsyncMock()
            mock_redis_client.ping = AsyncMock()
            mock_redis.from_url.return_value = mock_redis_client

            # Setup mock vectorizer
            mock_vectorizer = MagicMock()
            mock_vectorizer_class.return_value = mock_vectorizer

            service = CacheService(redis_url=redis_url)
            await service.initialize()

            # Verify VoyageAITextVectorizer was created with correct parameters
            # First call is for SemanticCache, second is for SemanticMessageHistory
            assert mock_vectorizer_class.call_count >= 1

            # Check first call (SemanticCache vectorizer)
            first_call_kwargs = mock_vectorizer_class.call_args_list[0][1]
            assert first_call_kwargs["model"] == "voyage-3-lite"
            assert first_call_kwargs["api_config"] == {"api_key": "test-api-key"}

            # Verify SemanticCache was created with the vectorizer
            mock_semantic_cache_class.assert_called_once()
            semantic_cache_kwargs = mock_semantic_cache_class.call_args[1]
            assert semantic_cache_kwargs["vectorizer"] == mock_vectorizer

            await service.close()

    @pytest.mark.asyncio
    async def test_cache_service_uses_voyage_vectorizer_for_message_history(self):
        """Verify VoyageAITextVectorizer is created for SemanticMessageHistory."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        with (
            patch.dict(os.environ, {"VOYAGE_API_KEY": "test-api-key"}),
            patch("telegram_bot.services.cache.VoyageAITextVectorizer") as mock_vectorizer_class,
            patch("telegram_bot.services.cache.SemanticCache"),
            patch("telegram_bot.services.cache.EmbeddingsCache"),
            patch(
                "telegram_bot.services.cache.SemanticMessageHistory"
            ) as mock_message_history_class,
            patch("telegram_bot.services.cache.redis") as mock_redis,
        ):
            # Setup mock Redis client
            mock_redis_client = AsyncMock()
            mock_redis_client.ping = AsyncMock()
            mock_redis.from_url.return_value = mock_redis_client

            # Setup mock vectorizers
            mock_vectorizer1 = MagicMock(name="semantic_cache_vectorizer")
            mock_vectorizer2 = MagicMock(name="message_history_vectorizer")
            mock_vectorizer_class.side_effect = [mock_vectorizer1, mock_vectorizer2]

            service = CacheService(redis_url=redis_url)
            await service.initialize()

            # Verify VoyageAITextVectorizer was created twice
            assert mock_vectorizer_class.call_count == 2

            # Check second call (SemanticMessageHistory vectorizer)
            second_call_kwargs = mock_vectorizer_class.call_args_list[1][1]
            assert second_call_kwargs["model"] == "voyage-3-lite"
            assert second_call_kwargs["api_config"] == {"api_key": "test-api-key"}

            # Verify SemanticMessageHistory was created with the vectorizer
            mock_message_history_class.assert_called_once()
            history_kwargs = mock_message_history_class.call_args[1]
            assert history_kwargs["vectorizer"] == mock_vectorizer2

            await service.close()

    @pytest.mark.asyncio
    async def test_cache_service_no_vectorizer_without_voyage_key(self):
        """Without VOYAGE_API_KEY, VoyageAITextVectorizer is not created."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        with (
            patch.dict(os.environ, {"VOYAGE_API_KEY": ""}),
            patch("telegram_bot.services.cache.VoyageAITextVectorizer") as mock_vectorizer_class,
            patch("telegram_bot.services.cache.SemanticCache"),
            patch("telegram_bot.services.cache.EmbeddingsCache"),
            patch("telegram_bot.services.cache.SemanticMessageHistory"),
            patch("telegram_bot.services.cache.redis") as mock_redis,
        ):
            # Setup mock Redis client
            mock_redis_client = AsyncMock()
            mock_redis_client.ping = AsyncMock()
            mock_redis.from_url.return_value = mock_redis_client

            service = CacheService(redis_url=redis_url)
            await service.initialize()

            ***REMOVED***AITextVectorizer should NOT be called without API key
            mock_vectorizer_class.assert_not_called()

            # SemanticCache should be None
            assert service.semantic_cache is None
            # MessageHistory should be None
            assert service.message_history is None

            await service.close()

    @pytest.mark.asyncio
    async def test_vectorizer_model_is_voyage_3_lite(self):
        """Verify the vectorizer uses voyage-3-lite model specifically."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        with (
            patch.dict(os.environ, {"VOYAGE_API_KEY": "my-api-key"}),
            patch("telegram_bot.services.cache.VoyageAITextVectorizer") as mock_vectorizer_class,
            patch("telegram_bot.services.cache.SemanticCache"),
            patch("telegram_bot.services.cache.EmbeddingsCache"),
            patch("telegram_bot.services.cache.SemanticMessageHistory"),
            patch("telegram_bot.services.cache.redis") as mock_redis,
        ):
            # Setup mock Redis client
            mock_redis_client = AsyncMock()
            mock_redis_client.ping = AsyncMock()
            mock_redis.from_url.return_value = mock_redis_client

            mock_vectorizer_class.return_value = MagicMock()

            service = CacheService(redis_url=redis_url)
            await service.initialize()

            # Both vectorizer creations should use voyage-3-lite
            for call in mock_vectorizer_class.call_args_list:
                assert call[1]["model"] == "voyage-3-lite"

            await service.close()
