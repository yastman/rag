"""Tests for CacheService including RerankCache."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.cache import CacheService


# Create mock modules for redisvl to avoid heavy imports
_mock_semantic_cache = MagicMock()
_mock_embeddings_cache = MagicMock()
_mock_message_history = MagicMock()
_mock_vectorizer = MagicMock()


class TestCacheServiceInitialize:
    """Tests for CacheService.initialize()."""

    @pytest.fixture
    def cache_service(self):
        return CacheService(redis_url="redis://localhost:6379")

    @pytest.fixture
    def mock_redisvl_modules(self):
        """Mock redisvl modules in sys.modules before import."""
        mock_llm = MagicMock()
        mock_llm.SemanticCache = _mock_semantic_cache
        mock_embeddings = MagicMock()
        mock_embeddings.EmbeddingsCache = _mock_embeddings_cache
        mock_history = MagicMock()
        mock_history.SemanticMessageHistory = _mock_message_history
        mock_vectorize = MagicMock()
        mock_vectorize.VoyageAITextVectorizer = _mock_vectorizer

        modules_to_mock = {
            "redisvl": MagicMock(),
            "redisvl.extensions": MagicMock(),
            "redisvl.extensions.cache": MagicMock(),
            "redisvl.extensions.cache.llm": mock_llm,
            "redisvl.extensions.cache.embeddings": mock_embeddings,
            "redisvl.extensions.message_history": mock_history,
            "redisvl.utils": MagicMock(),
            "redisvl.utils.vectorize": mock_vectorize,
        }

        with patch.dict(sys.modules, modules_to_mock):
            yield {
                "SemanticCache": _mock_semantic_cache,
                "EmbeddingsCache": _mock_embeddings_cache,
                "SemanticMessageHistory": _mock_message_history,
                "VoyageAITextVectorizer": _mock_vectorizer,
            }

    @pytest.mark.asyncio
    async def test_initialize_connects_to_redis(self, cache_service, mock_redisvl_modules):
        """Test that initialize() connects to Redis."""
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock(return_value=True)

        with patch("telegram_bot.services.cache.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_client
            with patch.dict("os.environ", {"VOYAGE_API_KEY": ""}):
                await cache_service.initialize()

            mock_redis_module.from_url.assert_called_once()
            mock_redis_client.ping.assert_called_once()
            assert cache_service.redis_client is mock_redis_client

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_error(self, cache_service, mock_redisvl_modules):
        """Test that initialize() handles connection errors gracefully."""
        with patch("telegram_bot.services.cache.redis") as mock_redis_module:
            mock_redis_module.from_url.side_effect = Exception("Connection refused")

            await cache_service.initialize()

            # Should not crash, redis_client should be None
            assert cache_service.redis_client is None

    @pytest.mark.asyncio
    async def test_initialize_sets_up_semantic_cache_with_api_key(
        self, cache_service, mock_redisvl_modules
    ):
        """Test that initialize() sets up SemanticCache when API key is available."""
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock(return_value=True)

        # Reset the mock to track calls
        mock_redisvl_modules["SemanticCache"].reset_mock()

        with patch("telegram_bot.services.cache.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_client
            with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-api-key"}):
                await cache_service.initialize()

            mock_redisvl_modules["SemanticCache"].assert_called_once()


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


class TestQueryAnalyzerCache:
    """Tests for QueryAnalyzer cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_analysis_hit(self, cache_service):
        """Test QueryAnalyzer cache hit."""
        analysis = {"filters": {"city": "Burgas"}, "semantic_query": "apartments"}
        cache_service.redis_client.get = AsyncMock(return_value=json.dumps(analysis))

        result = await cache_service.get_cached_analysis("test query")

        assert result == analysis
        assert cache_service.metrics["analyzer"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_analysis_miss(self, cache_service):
        """Test QueryAnalyzer cache miss."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_cached_analysis("test query")

        assert result is None
        assert cache_service.metrics["analyzer"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_analysis(self, cache_service):
        """Test storing analysis result."""
        cache_service.redis_client.setex = AsyncMock()
        analysis = {"filters": {}}

        await cache_service.store_analysis("query", analysis)

        cache_service.redis_client.setex.assert_called_once()


class TestSearchCache:
    """Tests for Search cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_search_hit(self, cache_service):
        """Test Search cache hit."""
        results = [{"id": 1, "text": "result"}]
        cache_service.redis_client.get = AsyncMock(return_value=json.dumps(results))

        result = await cache_service.get_cached_search(
            embedding=[0.1] * 10, filters={"city": "Burgas"}
        )

        assert result == results
        assert cache_service.metrics["search"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_store_search_results(self, cache_service):
        """Test storing search results."""
        cache_service.redis_client.setex = AsyncMock()

        await cache_service.store_search_results(
            embedding=[0.1] * 10, filters={}, results=[{"id": 1}]
        )

        cache_service.redis_client.setex.assert_called_once()


class TestSemanticMessageHistory:
    """Tests for Semantic Message History operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.message_history = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_relevant_history(self, cache_service):
        """Test getting relevant history messages."""
        messages = [{"role": "user", "content": "hello"}]
        cache_service.message_history.aget_relevant = AsyncMock(return_value=messages)

        result = await cache_service.get_relevant_history(user_id=123, query="hi")

        assert result == messages
        cache_service.message_history.aget_relevant.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_relevant_history_disabled(self, cache_service):
        """Test get_relevant_history returns empty list when disabled."""
        cache_service.message_history = None

        result = await cache_service.get_relevant_history(user_id=123, query="hi")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_relevant_history_error_handling(self, cache_service):
        """Test get_relevant_history handles errors gracefully."""
        cache_service.message_history.aget_relevant = AsyncMock(
            side_effect=Exception("Redis error")
        )

        result = await cache_service.get_relevant_history(user_id=123, query="hi")

        assert result == []

    @pytest.mark.asyncio
    async def test_add_semantic_message(self, cache_service):
        """Test adding message to semantic history."""
        cache_service.message_history.aadd_message = AsyncMock()

        await cache_service.add_semantic_message(user_id=123, role="user", content="hello")

        cache_service.message_history.aadd_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_semantic_message_disabled(self, cache_service):
        """Test add_semantic_message does nothing when disabled."""
        cache_service.message_history = None

        # Should not raise
        await cache_service.add_semantic_message(user_id=123, role="user", content="hello")

    @pytest.mark.asyncio
    async def test_add_semantic_message_error_handling(self, cache_service):
        """Test add_semantic_message handles errors gracefully."""
        cache_service.message_history.aadd_message = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise
        await cache_service.add_semantic_message(user_id=123, role="user", content="hello")


class TestHashKey:
    """Tests for _hash_key private method."""

    @pytest.fixture
    def cache_service(self):
        return CacheService(redis_url="redis://localhost:6379")

    def test_hash_key_returns_16_chars(self, cache_service):
        """Test _hash_key returns 16 character hash."""
        result = cache_service._hash_key("test data")

        assert len(result) == 16

    def test_hash_key_deterministic(self, cache_service):
        """Test _hash_key returns same hash for same input."""
        result1 = cache_service._hash_key("test data")
        result2 = cache_service._hash_key("test data")

        assert result1 == result2

    def test_hash_key_different_for_different_input(self, cache_service):
        """Test _hash_key returns different hash for different input."""
        result1 = cache_service._hash_key("test data 1")
        result2 = cache_service._hash_key("test data 2")

        assert result1 != result2


class TestLogMetrics:
    """Tests for log_metrics method."""

    @pytest.fixture
    def cache_service(self):
        return CacheService(redis_url="redis://localhost:6379")

    def test_log_metrics_does_not_raise(self, cache_service):
        """Test log_metrics doesn't raise with empty metrics."""
        # Should not raise
        cache_service.log_metrics()

    def test_log_metrics_with_data(self, cache_service):
        """Test log_metrics with actual metrics data."""
        cache_service.metrics["semantic"]["hits"] = 10
        cache_service.metrics["semantic"]["misses"] = 5

        # Should not raise
        cache_service.log_metrics()


class TestRerankCacheExtended:
    """Extended tests for Rerank cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_rerank_disabled(self, cache_service):
        """Test get_cached_rerank returns None when Redis disabled."""
        cache_service.redis_client = None

        result = await cache_service.get_cached_rerank(
            query_hash="abc123",
            chunk_ids=["chunk1"],
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_rerank_error_handling(self, cache_service):
        """Test get_cached_rerank handles errors gracefully."""
        cache_service.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await cache_service.get_cached_rerank(
            query_hash="abc123",
            chunk_ids=["chunk1"],
        )

        assert result is None
        assert cache_service.metrics["rerank"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_rerank_results_disabled(self, cache_service):
        """Test store_rerank_results does nothing when Redis disabled."""
        cache_service.redis_client = None

        # Should not raise
        await cache_service.store_rerank_results(
            query_hash="abc123",
            chunk_ids=["chunk1"],
            results=[{"id": "1", "score": 0.9}],
        )

    @pytest.mark.asyncio
    async def test_store_rerank_results_error_handling(self, cache_service):
        """Test store_rerank_results handles errors gracefully."""
        cache_service.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise
        await cache_service.store_rerank_results(
            query_hash="abc123",
            chunk_ids=["chunk1"],
            results=[{"id": "1", "score": 0.9}],
        )

    @pytest.mark.asyncio
    async def test_store_rerank_results_custom_ttl(self, cache_service):
        """Test store_rerank_results with custom TTL."""
        cache_service.redis_client.setex = AsyncMock()

        await cache_service.store_rerank_results(
            query_hash="abc123",
            chunk_ids=["chunk1"],
            results=[{"id": "1", "score": 0.9}],
            ttl=3600,
        )

        cache_service.redis_client.setex.assert_called_once()
        assert cache_service.redis_client.setex.call_args[0][1] == 3600


class TestSearchCacheExtended:
    """Extended tests for Search cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_search_miss(self, cache_service):
        """Test Search cache miss."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_cached_search(
            embedding=[0.1] * 10, filters={"city": "Burgas"}
        )

        assert result is None
        assert cache_service.metrics["search"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_search_disabled(self, cache_service):
        """Test get_cached_search returns None when Redis disabled."""
        cache_service.redis_client = None

        result = await cache_service.get_cached_search(embedding=[0.1] * 10, filters=None)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_search_error_handling(self, cache_service):
        """Test get_cached_search handles errors gracefully."""
        cache_service.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await cache_service.get_cached_search(embedding=[0.1] * 10, filters=None)

        assert result is None
        assert cache_service.metrics["search"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_search_with_index_version(self, cache_service):
        """Test get_cached_search with custom index version."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        await cache_service.get_cached_search(
            embedding=[0.1] * 10, filters=None, index_version="v2"
        )

        cache_service.redis_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_search_results_disabled(self, cache_service):
        """Test store_search_results does nothing when Redis disabled."""
        cache_service.redis_client = None

        # Should not raise
        await cache_service.store_search_results(
            embedding=[0.1] * 10, filters={}, results=[{"id": 1}]
        )

    @pytest.mark.asyncio
    async def test_store_search_results_error_handling(self, cache_service):
        """Test store_search_results handles errors gracefully."""
        cache_service.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise
        await cache_service.store_search_results(
            embedding=[0.1] * 10, filters={}, results=[{"id": 1}]
        )

    @pytest.mark.asyncio
    async def test_store_search_results_with_none_filters(self, cache_service):
        """Test store_search_results with None filters."""
        cache_service.redis_client.setex = AsyncMock()

        await cache_service.store_search_results(
            embedding=[0.1] * 10, filters=None, results=[{"id": 1}]
        )

        cache_service.redis_client.setex.assert_called_once()


class TestQueryAnalyzerCacheExtended:
    """Extended tests for QueryAnalyzer cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_cached_analysis_disabled(self, cache_service):
        """Test get_cached_analysis returns None when Redis disabled."""
        cache_service.redis_client = None

        result = await cache_service.get_cached_analysis("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_analysis_error_handling(self, cache_service):
        """Test get_cached_analysis handles errors gracefully."""
        cache_service.redis_client.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await cache_service.get_cached_analysis("test query")

        assert result is None
        assert cache_service.metrics["analyzer"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_analysis_disabled(self, cache_service):
        """Test store_analysis does nothing when Redis disabled."""
        cache_service.redis_client = None

        # Should not raise
        await cache_service.store_analysis("query", {"filters": {}})

    @pytest.mark.asyncio
    async def test_store_analysis_error_handling(self, cache_service):
        """Test store_analysis handles errors gracefully."""
        cache_service.redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise
        await cache_service.store_analysis("query", {"filters": {}})


class TestConversationHistoryExtended:
    """Extended tests for conversation history operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_store_conversation_message_with_pipeline(self, cache_service):
        """Test store_conversation_message executes Redis pipeline operations."""
        cache_service.redis_client.lpush = AsyncMock()
        cache_service.redis_client.ltrim = AsyncMock()
        cache_service.redis_client.expire = AsyncMock()

        await cache_service.store_conversation_message(123, "assistant", "goodbye")

        # Verify all pipeline operations were called
        cache_service.redis_client.lpush.assert_called_once()
        cache_service.redis_client.ltrim.assert_called_once()
        cache_service.redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_conversation_history_json_parsing(self, cache_service):
        """Test get_conversation_history parses JSON messages correctly."""
        cache_service.redis_client.lrange = AsyncMock(
            return_value=['{"role": "user", "content": "test message", "timestamp": 1234567890.0}']
        )

        result = await cache_service.get_conversation_history(user_id=456)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "test message"
        assert result[0]["timestamp"] == 1234567890.0


class TestCacheServiceInitExtended:
    """Extended tests for CacheService constructor."""

    def test_init_with_custom_ttls(self):
        """Test CacheService initializes with custom TTL values."""
        service = CacheService(
            redis_url="redis://localhost:6379",
            semantic_cache_ttl=7200,
            embeddings_cache_ttl=14400,
            analyzer_cache_ttl=3600,
            search_cache_ttl=1800,
            distance_threshold=0.10,
        )

        assert service.semantic_cache_ttl == 7200
        assert service.embeddings_cache_ttl == 14400
        assert service.analyzer_cache_ttl == 3600
        assert service.search_cache_ttl == 1800
        assert service.distance_threshold == 0.10

    def test_init_default_ttls(self):
        """Test CacheService initializes with default TTL values."""
        service = CacheService(redis_url="redis://localhost:6379")

        assert service.semantic_cache_ttl == 48 * 3600  # 48 hours
        assert service.embeddings_cache_ttl == 7 * 24 * 3600  # 7 days
        assert service.analyzer_cache_ttl == 24 * 3600  # 24 hours
        assert service.search_cache_ttl == 2 * 3600  # 2 hours
        assert service.distance_threshold == 0.20  # Relaxed for RU paraphrases

    def test_init_creates_empty_metrics(self):
        """Test CacheService initializes with empty metrics for all cache types."""
        service = CacheService(redis_url="redis://localhost:6379")

        assert "semantic" in service.metrics
        assert "embeddings" in service.metrics
        assert "analyzer" in service.metrics
        assert "search" in service.metrics
        assert "rerank" in service.metrics

        for cache_type in service.metrics:
            assert service.metrics[cache_type]["hits"] == 0
            assert service.metrics[cache_type]["misses"] == 0


class TestCacheServiceUserBase:
    """Tests for USER-base integration in CacheService."""

    def test_default_threshold_is_relaxed(self):
        """Should use 0.20 threshold for better RU paraphrase matching."""
        cache = CacheService(redis_url="redis://localhost:6379")
        assert cache.distance_threshold == 0.20


class TestCloseExtended:
    """Extended tests for CacheService.close()."""

    @pytest.mark.asyncio
    async def test_close_handles_none_clients(self):
        """Test close() handles None clients gracefully."""
        service = CacheService(redis_url="redis://localhost:6379")
        service.semantic_cache = None
        service.embeddings_cache = None
        service.redis_client = None

        # Should not raise
        await service.close()

    @pytest.mark.asyncio
    async def test_close_handles_partial_clients(self):
        """Test close() handles partially initialized clients."""
        service = CacheService(redis_url="redis://localhost:6379")
        service.semantic_cache = AsyncMock()
        service.embeddings_cache = None
        service.redis_client = AsyncMock()

        await service.close()

        service.semantic_cache.adisconnect.assert_called_once()
        service.redis_client.aclose.assert_called_once()
