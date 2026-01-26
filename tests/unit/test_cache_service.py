"""Tests for CacheService including RerankCache."""

from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.cache import CacheService


class TestCacheServiceInitialize:
    """Tests for CacheService.initialize()."""

    @pytest.fixture
    def cache_service(self):
        return CacheService(redis_url="redis://localhost:6379")

    @pytest.mark.asyncio
    async def test_initialize_connects_to_redis(self, cache_service):
        """Test that initialize() connects to Redis."""
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_client

            # Mock SemanticCache and EmbeddingsCache to avoid external dependencies
            with patch("telegram_bot.services.cache.SemanticCache"):
                with patch("telegram_bot.services.cache.EmbeddingsCache"):
                    with patch("telegram_bot.services.cache.SemanticMessageHistory"):
                        with patch.dict("os.environ", {"VOYAGE_API_KEY": ""}):
                            await cache_service.initialize()

            mock_redis_module.from_url.assert_called_once()
            mock_redis_client.ping.assert_called_once()
            assert cache_service.redis_client is mock_redis_client

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_error(self, cache_service):
        """Test that initialize() handles connection errors gracefully."""
        with patch("telegram_bot.services.cache.redis") as mock_redis_module:
            mock_redis_module.from_url.side_effect = Exception("Connection refused")

            await cache_service.initialize()

            # Should not crash, redis_client should be None
            assert cache_service.redis_client is None

    @pytest.mark.asyncio
    async def test_initialize_sets_up_semantic_cache_with_api_key(self, cache_service):
        """Test that initialize() sets up SemanticCache when API key is available."""
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_client

            with patch("telegram_bot.services.cache.SemanticCache") as mock_semantic_cache:
                with patch("telegram_bot.services.cache.EmbeddingsCache"):
                    with patch("telegram_bot.services.cache.SemanticMessageHistory"):
                        with patch("telegram_bot.services.cache.VoyageAITextVectorizer"):
                            with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-api-key"}):
                                await cache_service.initialize()

                mock_semantic_cache.assert_called_once()


class TestSemanticCache:
    """Tests for semantic cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        service.semantic_cache = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_check_semantic_cache_hit(self, cache_service):
        """Test semantic cache hit returns cached answer."""
        cache_service.semantic_cache.acheck = AsyncMock(
            return_value=[{"response": "cached response", "vector_distance": 0.05}]
        )

        result = await cache_service.check_semantic_cache("test query")

        assert result == "cached response"
        assert cache_service.metrics["semantic"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_check_semantic_cache_miss(self, cache_service):
        """Test semantic cache miss returns None."""
        cache_service.semantic_cache.acheck = AsyncMock(return_value=[])

        result = await cache_service.check_semantic_cache("test query")

        assert result is None
        assert cache_service.metrics["semantic"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_check_semantic_cache_with_user_filter(self, cache_service):
        """Test semantic cache with user_id filter."""
        cache_service.semantic_cache.acheck = AsyncMock(return_value=[])

        await cache_service.check_semantic_cache("test query", user_id=123)

        # Verify acheck was called with filter expression
        cache_service.semantic_cache.acheck.assert_called_once()
        call_kwargs = cache_service.semantic_cache.acheck.call_args[1]
        assert call_kwargs["prompt"] == "test query"
        assert "filter_expression" in call_kwargs

    @pytest.mark.asyncio
    async def test_check_semantic_cache_with_threshold_override(self, cache_service):
        """Test semantic cache with custom threshold."""
        cache_service.semantic_cache.acheck = AsyncMock(return_value=[])

        await cache_service.check_semantic_cache("test query", threshold_override=0.05)

        call_kwargs = cache_service.semantic_cache.acheck.call_args[1]
        assert call_kwargs["distance_threshold"] == 0.05

    @pytest.mark.asyncio
    async def test_check_semantic_cache_disabled(self, cache_service):
        """Test semantic cache returns None when disabled."""
        cache_service.semantic_cache = None

        result = await cache_service.check_semantic_cache("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_check_semantic_cache_error_handling(self, cache_service):
        """Test semantic cache handles errors gracefully."""
        cache_service.semantic_cache.acheck = AsyncMock(side_effect=Exception("API error"))

        result = await cache_service.check_semantic_cache("test query")

        assert result is None
        assert cache_service.metrics["semantic"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_semantic_cache(self, cache_service):
        """Test storing in semantic cache."""
        cache_service.semantic_cache.astore = AsyncMock()

        await cache_service.store_semantic_cache("query", "answer")

        cache_service.semantic_cache.astore.assert_called_once()
        call_kwargs = cache_service.semantic_cache.astore.call_args[1]
        assert call_kwargs["prompt"] == "query"
        assert call_kwargs["response"] == "answer"

    @pytest.mark.asyncio
    async def test_store_semantic_cache_with_user_id(self, cache_service):
        """Test storing in semantic cache with user_id."""
        cache_service.semantic_cache.astore = AsyncMock()

        await cache_service.store_semantic_cache("query", "answer", user_id=123)

        call_kwargs = cache_service.semantic_cache.astore.call_args[1]
        assert call_kwargs["filters"]["user_id"] == "123"

    @pytest.mark.asyncio
    async def test_store_semantic_cache_disabled(self, cache_service):
        """Test store does nothing when semantic cache is disabled."""
        cache_service.semantic_cache = None

        # Should not raise
        await cache_service.store_semantic_cache("query", "answer")


class TestEmbeddingCache:
    """Tests for embedding cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        service.embeddings_cache = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_embedding_hit(self, cache_service):
        """Test embedding cache hit."""
        cache_service.embeddings_cache.aget = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})

        result = await cache_service.get_cached_embedding("test query")

        assert result == [0.1, 0.2, 0.3]
        assert cache_service.metrics["embeddings"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_embedding_miss(self, cache_service):
        """Test embedding cache miss."""
        cache_service.embeddings_cache.aget = AsyncMock(return_value=None)

        result = await cache_service.get_cached_embedding("test query")

        assert result is None
        assert cache_service.metrics["embeddings"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_embedding_with_model_name(self, cache_service):
        """Test embedding cache with custom model name."""
        cache_service.embeddings_cache.aget = AsyncMock(return_value=None)

        await cache_service.get_cached_embedding("test query", model_name="voyage-4")

        call_kwargs = cache_service.embeddings_cache.aget.call_args[1]
        assert call_kwargs["model_name"] == "voyage-4"

    @pytest.mark.asyncio
    async def test_get_cached_embedding_disabled(self, cache_service):
        """Test embedding cache returns None when disabled."""
        cache_service.embeddings_cache = None

        result = await cache_service.get_cached_embedding("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_embedding_error_handling(self, cache_service):
        """Test embedding cache handles errors gracefully."""
        cache_service.embeddings_cache.aget = AsyncMock(side_effect=Exception("Redis error"))

        result = await cache_service.get_cached_embedding("test query")

        assert result is None
        assert cache_service.metrics["embeddings"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_embedding(self, cache_service):
        """Test storing embedding."""
        cache_service.embeddings_cache.aset = AsyncMock()

        await cache_service.store_embedding("query", [0.1, 0.2, 0.3])

        cache_service.embeddings_cache.aset.assert_called_once()
        call_kwargs = cache_service.embeddings_cache.aset.call_args[1]
        assert call_kwargs["content"] == "query"
        assert call_kwargs["embedding"] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_store_embedding_with_metadata(self, cache_service):
        """Test storing embedding with metadata."""
        cache_service.embeddings_cache.aset = AsyncMock()

        await cache_service.store_embedding("query", [0.1, 0.2, 0.3], metadata={"source": "test"})

        call_kwargs = cache_service.embeddings_cache.aset.call_args[1]
        assert call_kwargs["metadata"] == {"source": "test"}

    @pytest.mark.asyncio
    async def test_store_embedding_disabled(self, cache_service):
        """Test store does nothing when embeddings cache is disabled."""
        cache_service.embeddings_cache = None

        # Should not raise
        await cache_service.store_embedding("query", [0.1, 0.2, 0.3])


class TestConversationHistory:
    """Tests for conversation history operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, cache_service):
        """Test getting conversation history."""
        cache_service.redis_client.lrange = AsyncMock(
            return_value=[
                '{"role": "user", "content": "hello", "timestamp": 123}',
                '{"role": "assistant", "content": "hi", "timestamp": 124}',
            ]
        )

        result = await cache_service.get_conversation_history(user_id=123, last_n=5)

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hello"
        cache_service.redis_client.lrange.assert_called_once_with("conversation:123", 0, 4)

    @pytest.mark.asyncio
    async def test_get_conversation_history_empty(self, cache_service):
        """Test getting empty conversation history."""
        cache_service.redis_client.lrange = AsyncMock(return_value=[])

        result = await cache_service.get_conversation_history(user_id=123)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_conversation_history_disabled(self, cache_service):
        """Test conversation history returns empty when Redis disabled."""
        cache_service.redis_client = None

        result = await cache_service.get_conversation_history(user_id=123)

        assert result == []

    @pytest.mark.asyncio
    async def test_store_conversation_message(self, cache_service):
        """Test storing conversation message."""
        cache_service.redis_client.lpush = AsyncMock()
        cache_service.redis_client.ltrim = AsyncMock()
        cache_service.redis_client.expire = AsyncMock()

        await cache_service.store_conversation_message(123, "user", "hello")

        cache_service.redis_client.lpush.assert_called_once()
        cache_service.redis_client.ltrim.assert_called_once_with("conversation:123", 0, 9)
        cache_service.redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_conversation_message_with_custom_params(self, cache_service):
        """Test storing conversation message with custom max_messages and ttl."""
        cache_service.redis_client.lpush = AsyncMock()
        cache_service.redis_client.ltrim = AsyncMock()
        cache_service.redis_client.expire = AsyncMock()

        await cache_service.store_conversation_message(
            123, "user", "hello", max_messages=20, ttl=7200
        )

        cache_service.redis_client.ltrim.assert_called_once_with("conversation:123", 0, 19)
        cache_service.redis_client.expire.assert_called_once_with("conversation:123", 7200)

    @pytest.mark.asyncio
    async def test_store_conversation_message_disabled(self, cache_service):
        """Test store does nothing when Redis disabled."""
        cache_service.redis_client = None

        # Should not raise
        await cache_service.store_conversation_message(123, "user", "hello")

    @pytest.mark.asyncio
    async def test_clear_conversation_history(self, cache_service):
        """Test clearing conversation history."""
        cache_service.redis_client.delete = AsyncMock()

        await cache_service.clear_conversation_history(123)

        cache_service.redis_client.delete.assert_called_once_with("conversation:123")

    @pytest.mark.asyncio
    async def test_clear_conversation_history_disabled(self, cache_service):
        """Test clear does nothing when Redis disabled."""
        cache_service.redis_client = None

        # Should not raise
        await cache_service.clear_conversation_history(123)


class TestCacheServiceMetrics:
    """Tests for cache metrics."""

    @pytest.fixture
    def cache_service(self):
        return CacheService(redis_url="redis://localhost:6379")

    def test_get_metrics_initial(self, cache_service):
        """Test initial metrics are zero."""
        metrics = cache_service.get_metrics()

        assert metrics["total_hits"] == 0
        assert metrics["total_misses"] == 0
        assert metrics["overall_hit_rate"] == 0

    def test_get_metrics_with_hits(self, cache_service):
        """Test metrics after cache hits."""
        cache_service.metrics["semantic"]["hits"] = 5
        cache_service.metrics["semantic"]["misses"] = 5

        metrics = cache_service.get_metrics()

        assert metrics["total_hits"] == 5
        assert metrics["total_misses"] == 5
        assert metrics["by_type"]["semantic"]["hit_rate"] == 50.0

    def test_get_metrics_multiple_caches(self, cache_service):
        """Test metrics from multiple cache types."""
        cache_service.metrics["semantic"]["hits"] = 10
        cache_service.metrics["embeddings"]["hits"] = 5
        cache_service.metrics["rerank"]["hits"] = 3

        metrics = cache_service.get_metrics()

        assert metrics["total_hits"] == 18
        assert metrics["total_requests"] == 18


class TestCacheServiceClose:
    """Tests for CacheService.close()."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        service.semantic_cache = AsyncMock()
        service.embeddings_cache = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_close_disconnects_all(self, cache_service):
        """Test close() disconnects all Redis connections."""
        await cache_service.close()

        cache_service.semantic_cache.adisconnect.assert_called_once()
        cache_service.embeddings_cache.adisconnect.assert_called_once()
        cache_service.redis_client.aclose.assert_called_once()


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
