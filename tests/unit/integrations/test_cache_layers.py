"""Tests for CacheLayerManager — 6-tier Redis cache rewrite."""

import asyncio
import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.integrations.cache import CacheLayerManager


def _ensure_redisvl_filter_mock():
    """Ensure redisvl.query.filter.Tag is importable (mock if needed)."""
    if "redisvl.query.filter" not in sys.modules:
        # Create minimal mock module chain
        redisvl_mod = sys.modules.get("redisvl") or ModuleType("redisvl")
        query_mod = ModuleType("redisvl.query")
        filter_mod = ModuleType("redisvl.query.filter")

        class MockTag:
            def __init__(self, name):
                self.name = name

            def __eq__(self, other):
                return MagicMock()

        filter_mod.Tag = MockTag  # type: ignore[attr-defined]
        sys.modules.setdefault("redisvl", redisvl_mod)
        sys.modules.setdefault("redisvl.query", query_mod)
        sys.modules["redisvl.query.filter"] = filter_mod


class TestCacheLayerManagerInit:
    """Test initialization and configuration."""

    def test_creates_with_defaults(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        assert mgr.redis_url == "redis://localhost:6379"
        assert mgr.redis is None
        assert mgr.semantic_cache is None

    def test_metrics_initialized(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        metrics = mgr.get_metrics()
        assert "semantic" in metrics
        assert "embeddings" in metrics
        assert "search" in metrics
        assert metrics["semantic"]["hits"] == 0
        assert metrics["semantic"]["misses"] == 0

    def test_custom_thresholds(self):
        thresholds = {"FAQ": 0.15, "GENERAL": 0.10}
        mgr = CacheLayerManager(
            redis_url="redis://localhost:6379",
            cache_thresholds=thresholds,
        )
        assert mgr.cache_thresholds["FAQ"] == 0.15
        assert mgr.cache_thresholds["GENERAL"] == 0.10


class TestCacheLayerManagerInitialize:
    """Test async initialization."""

    @pytest.mark.asyncio
    async def test_initialize_uses_hardened_connection_params(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch(
                "telegram_bot.integrations.cache.redis.from_url", return_value=mock_redis
            ) as mock_from_url,
            patch("telegram_bot.integrations.cache._create_semantic_cache", return_value=None),
        ):
            await mgr.initialize()

        call_kwargs = mock_from_url.call_args[1]
        assert call_kwargs["socket_timeout"] == 5
        assert call_kwargs["socket_connect_timeout"] == 5
        assert call_kwargs["retry_on_timeout"] is True
        assert call_kwargs["health_check_interval"] == 30

        from redis.retry import Retry

        assert isinstance(call_kwargs["retry"], Retry)

    @pytest.mark.asyncio
    async def test_initialize_connects_redis(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("telegram_bot.integrations.cache.redis.from_url", return_value=mock_redis),
            patch("telegram_bot.integrations.cache._create_semantic_cache", return_value=None),
        ):
            await mgr.initialize()

        assert mgr.redis is mock_redis
        mock_redis.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_graceful_on_failure(self):
        mgr = CacheLayerManager(redis_url="redis://bad:6379")

        with patch(
            "telegram_bot.integrations.cache.redis.from_url",
            side_effect=ConnectionError("refused"),
        ):
            await mgr.initialize()

        assert mgr.redis is None


class TestSemanticCache:
    """Test semantic cache check/store."""

    @pytest.mark.asyncio
    async def test_semantic_miss_returns_none(self):
        _ensure_redisvl_filter_mock()
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = AsyncMock()
        mgr.semantic_cache.acheck = AsyncMock(return_value=[])

        result = await mgr.check_semantic(
            query="test query",
            vector=[0.1] * 1024,
            query_type="GENERAL",
        )
        assert result is None
        assert mgr._metrics["semantic"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_semantic_hit_returns_response(self):
        _ensure_redisvl_filter_mock()
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = AsyncMock()
        mgr.semantic_cache.acheck = AsyncMock(
            return_value=[{"response": "cached answer", "vector_distance": 0.05}]
        )

        mgr.cache_thresholds = {"FAQ": 0.12, "GENERAL": 0.08}

        result = await mgr.check_semantic(
            query="test query",
            vector=[0.1] * 1024,
            query_type="FAQ",
        )
        assert result == "cached answer"
        assert mgr._metrics["semantic"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_semantic_timeout_returns_none(self):
        _ensure_redisvl_filter_mock()
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = AsyncMock()

        async def slow_check(**kwargs):
            await asyncio.sleep(1.0)
            return [{"response": "slow"}]

        mgr.semantic_cache.acheck = slow_check
        mgr.cache_thresholds = {"GENERAL": 0.08}

        result = await mgr.check_semantic(
            query="test",
            vector=[0.1] * 1024,
            query_type="GENERAL",
            cache_timeout=0.01,
        )
        assert result is None
        assert mgr._metrics["semantic"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_semantic_store(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = AsyncMock()
        mgr.semantic_cache.astore = AsyncMock()
        mgr.cache_thresholds = {"GENERAL": 0.08}
        mgr.cache_ttl = {"GENERAL": 3600}

        await mgr.store_semantic(
            query="test query",
            response="test response",
            vector=[0.1] * 1024,
            query_type="GENERAL",
        )
        mgr.semantic_cache.astore.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_semantic_check_filters_by_user_id(self):
        """check_semantic with user_id builds combined Tag filter (user_id + language)."""
        _ensure_redisvl_filter_mock()
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = AsyncMock()
        mgr.semantic_cache.acheck = AsyncMock(return_value=[])
        mgr.cache_thresholds = {"FAQ": 0.12}

        await mgr.check_semantic(
            query="test query",
            vector=[0.1] * 1024,
            query_type="FAQ",
            user_id=42,
        )

        call_kwargs = mgr.semantic_cache.acheck.call_args[1]
        # filter_expression should be present (combined Tag filter)
        assert "filter_expression" in call_kwargs

    @pytest.mark.asyncio
    async def test_semantic_store_includes_user_id_in_filters(self):
        """store_semantic with user_id passes user_id string in filters dict."""
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = AsyncMock()
        mgr.semantic_cache.astore = AsyncMock()
        mgr.cache_ttl = {"FAQ": 86400}

        await mgr.store_semantic(
            query="test query",
            response="test response",
            vector=[0.1] * 1024,
            query_type="FAQ",
            user_id=42,
        )

        call_kwargs = mgr.semantic_cache.astore.call_args[1]
        assert call_kwargs["filters"]["user_id"] == "42"

    @pytest.mark.asyncio
    async def test_semantic_check_disabled_returns_none(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = None

        result = await mgr.check_semantic(query="test", vector=[0.1] * 1024, query_type="GENERAL")
        assert result is None


class TestExactCaches:
    """Test exact key-value caches (embeddings, sparse, analysis, search, rerank)."""

    @pytest.mark.asyncio
    async def test_exact_store_and_get(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        mgr.redis.get = AsyncMock(return_value=json.dumps([0.1, 0.2, 0.3]))
        mgr.redis.setex = AsyncMock()

        # Store
        await mgr.store_exact("embeddings", "key1", [0.1, 0.2, 0.3])
        mgr.redis.setex.assert_awaited_once()

        # Get
        result = await mgr.get_exact("embeddings", "key1")
        assert result == [0.1, 0.2, 0.3]
        assert mgr._metrics["embeddings"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_exact_miss(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        mgr.redis.get = AsyncMock(return_value=None)

        result = await mgr.get_exact("search", "nonexistent")
        assert result is None
        assert mgr._metrics["search"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_exact_disabled_returns_none(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = None

        result = await mgr.get_exact("embeddings", "key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_cache_with_hash_key(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        cached_docs = [{"id": "1", "text": "doc", "score": 0.9}]
        mgr.redis.get = AsyncMock(return_value=json.dumps(cached_docs))

        result = await mgr.get_exact("search", "some_hash")
        assert result == cached_docs
        assert mgr._metrics["search"]["hits"] == 1


def _make_pipeline_mock():
    """Create a mock Redis pipeline with async context manager support."""
    pipe = AsyncMock()
    pipe.lpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[True, True, True])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    return pipe


class TestConversationHistory:
    """Test conversation history (Redis LIST)."""

    @pytest.mark.asyncio
    async def test_store_conversation(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        pipe = _make_pipeline_mock()
        mgr.redis = AsyncMock()
        mgr.redis.pipeline = MagicMock(return_value=pipe)

        await mgr.store_conversation(user_id=123, role="user", content="hello")

        pipe.lpush.assert_called_once()
        pipe.ltrim.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_conversation_batch(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        pipe = _make_pipeline_mock()
        mgr.redis = AsyncMock()
        mgr.redis.pipeline = MagicMock(return_value=pipe)

        await mgr.store_conversation_batch(
            user_id=123,
            messages=[("user", "hello"), ("assistant", "hi")],
        )

        # 2 lpush calls (one per message), 1 ltrim, 1 expire
        assert pipe.lpush.call_count == 2
        pipe.ltrim.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_conversation_batch_empty(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        mgr.redis.pipeline = MagicMock()

        await mgr.store_conversation_batch(user_id=123, messages=[])

        mgr.redis.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_conversation_batch_disabled(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = None

        # Should not raise
        await mgr.store_conversation_batch(user_id=123, messages=[("user", "hi")])

    @pytest.mark.asyncio
    async def test_get_conversation(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        msgs = [
            json.dumps({"role": "user", "content": "hello"}),
            json.dumps({"role": "assistant", "content": "hi"}),
        ]
        mgr.redis.lrange = AsyncMock(return_value=msgs)

        result = await mgr.get_conversation(user_id=123, last_n=5)
        assert len(result) == 2
        assert result[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_conversation_empty(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        mgr.redis.lrange = AsyncMock(return_value=[])

        result = await mgr.get_conversation(user_id=123)
        assert result == []

    @pytest.mark.asyncio
    async def test_conversation_disabled(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = None

        await mgr.store_conversation(user_id=123, role="user", content="hi")
        result = await mgr.get_conversation(user_id=123)
        assert result == []


class TestMetrics:
    """Test metrics collection."""

    def test_get_metrics_empty(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        metrics = mgr.get_metrics()
        assert metrics["overall_hit_rate"] == 0.0
        assert metrics["total_requests"] == 0

    @pytest.mark.asyncio
    async def test_metrics_accumulate(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = AsyncMock()
        mgr.redis.get = AsyncMock(return_value=None)

        await mgr.get_exact("embeddings", "k1")
        await mgr.get_exact("embeddings", "k2")

        metrics = mgr.get_metrics()
        assert metrics["embeddings"]["misses"] == 2
        assert metrics["total_requests"] == 2
