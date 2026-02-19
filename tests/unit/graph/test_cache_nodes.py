"""Tests for cache_check_node and cache_store_node."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


@pytest.fixture(autouse=True)
def _ensure_redisvl_mock(monkeypatch):
    """Ensure redisvl modules are importable (mock if needed) — fixture-scoped."""
    try:
        import redisvl.query.filter  # noqa: F401

        return
    except (ImportError, ModuleNotFoundError):
        pass

    redisvl_mod = sys.modules.get("redisvl") or ModuleType("redisvl")
    query_mod = ModuleType("redisvl.query")
    filter_mod = ModuleType("redisvl.query.filter")

    class MockTag:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return MagicMock()

    filter_mod.Tag = MockTag  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redisvl", redisvl_mod)
    monkeypatch.setitem(sys.modules, "redisvl.query", query_mod)
    monkeypatch.setitem(sys.modules, "redisvl.query.filter", filter_mod)


from telegram_bot.graph.nodes.cache import (
    CACHEABLE_QUERY_TYPES,
    cache_check_node,
    cache_store_node,
)
from telegram_bot.graph.state import make_initial_state


def _make_mock_config():
    """Create a mock GraphConfig with cache dependencies."""
    config = MagicMock()
    config.cache_thresholds = {"FAQ": 0.12, "GENERAL": 0.08}
    config.cache_ttl = {"FAQ": 86400, "GENERAL": 3600}
    config.bge_m3_url = "http://bge-m3:8000"
    return config


class TestCacheCheckNode:
    """Test cache_check_node."""

    async def test_miss_path_computes_embedding(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.check_semantic = AsyncMock(return_value=None)
        cache.get_embedding = AsyncMock(return_value=None)

        # Non-hybrid embeddings (no aembed_hybrid attr)
        embeddings = AsyncMock(spec=["aembed_query"])
        embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1024)

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["cache_hit"] is False
        assert result["cached_response"] is None
        assert result["query_embedding"] == [0.1] * 1024
        embeddings.aembed_query.assert_awaited_once_with("test query")

    async def test_general_uses_semantic_cache(self):
        """GENERAL query type should call check_semantic (now in allowlist, threshold 0.08)."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"

        cache = AsyncMock()
        cache.check_semantic = AsyncMock(return_value=None)
        cache.get_embedding = AsyncMock(return_value=None)

        embeddings = AsyncMock(spec=["aembed_query"])
        embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1024)

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["cache_hit"] is False
        cache.check_semantic.assert_awaited_once()

    async def test_hit_path_returns_cached(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.2] * 1024)
        cache.check_semantic = AsyncMock(return_value="cached answer")

        embeddings = AsyncMock()

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["cache_hit"] is True
        assert result["cached_response"] == "cached answer"
        assert result["query_embedding"] == [0.2] * 1024
        # Should use cached embedding, not recompute
        embeddings.aembed_query.assert_not_awaited()

    async def test_check_does_not_pass_user_id_to_cache(self):
        """cache_check_node does NOT pass user_id to check_semantic (global cache)."""
        state = make_initial_state(user_id=99, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.2] * 1024)
        cache.check_semantic = AsyncMock(return_value=None)

        embeddings = AsyncMock()

        await cache_check_node(state, cache=cache, embeddings=embeddings)

        call_kwargs = cache.check_semantic.call_args[1]
        assert "user_id" not in call_kwargs

    async def test_stores_new_embedding_in_cache(self):
        state = make_initial_state(user_id=1, session_id="s1", query="new query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.check_semantic = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()

        # Non-hybrid embeddings (no aembed_hybrid attr)
        embeddings = AsyncMock(spec=["aembed_query"])
        embeddings.aembed_query = AsyncMock(return_value=[0.3] * 1024)

        await cache_check_node(state, cache=cache, embeddings=embeddings)

        cache.store_embedding.assert_awaited_once_with("new query", [0.3] * 1024)

    async def test_hybrid_stores_both_embeddings(self):
        """When hybrid embeddings available, cache both dense and sparse."""
        state = make_initial_state(user_id=1, session_id="s1", query="hybrid query")
        state["query_type"] = "ENTITY"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.check_semantic = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()

        sparse_vec = {"indices": [1, 5], "values": [0.1, 0.5]}
        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(return_value=([0.3] * 1024, sparse_vec))

        await cache_check_node(state, cache=cache, embeddings=embeddings)

        cache.store_embedding.assert_awaited_once_with("hybrid query", [0.3] * 1024)
        cache.store_sparse_embedding.assert_awaited_once_with("hybrid query", sparse_vec)


class TestCacheStoreNode:
    """Test cache_store_node."""

    async def test_stores_response_in_semantic_cache(self):
        """FAQ (allowlisted) stores to semantic cache without user_id (global)."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = "generated answer"

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        result = await cache_store_node(state, cache=cache)

        cache.store_semantic.assert_awaited_once_with(
            query="test query",
            response="generated answer",
            vector=[0.1] * 1024,
            query_type="FAQ",
        )
        assert result["response"] == "generated answer"

    async def test_general_stores_to_semantic_cache(self):
        """GENERAL query type should call store_semantic (now in allowlist, threshold 0.08)."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = "generated answer"

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        result = await cache_store_node(state, cache=cache)

        cache.store_semantic.assert_awaited_once()
        assert result["response"] == "generated answer"

    async def test_store_passes_user_id_to_cache(self):
        """cache_store_node does NOT pass user_id to store_semantic (global cache)."""
        state = make_initial_state(user_id=99, session_id="s1", query="test query")
        state["query_type"] = "FAQ"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = "generated answer"

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        await cache_store_node(state, cache=cache)

        call_kwargs = cache.store_semantic.call_args[1]
        assert "user_id" not in call_kwargs

    async def test_skips_store_if_no_response(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024
        state["response"] = ""

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        result = await cache_store_node(state, cache=cache)

        cache.store_semantic.assert_not_awaited()
        assert result["response"] == ""

    async def test_skips_store_if_no_embedding(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = None
        state["response"] = "answer"

        cache = AsyncMock()
        cache.store_semantic = AsyncMock()

        await cache_store_node(state, cache=cache)

        cache.store_semantic.assert_not_awaited()


class TestCacheableQueryTypes:
    """Test CACHEABLE_QUERY_TYPES constant."""

    def test_allowlist_contains_expected_types(self):
        assert "FAQ" in CACHEABLE_QUERY_TYPES
        assert "ENTITY" in CACHEABLE_QUERY_TYPES
        assert "STRUCTURED" in CACHEABLE_QUERY_TYPES

    def test_allowlist_includes_general(self):
        """GENERAL is now cacheable with threshold 0.08 (#477)."""
        assert "GENERAL" in CACHEABLE_QUERY_TYPES

    def test_allowlist_excludes_non_rag_types(self):
        assert "CHITCHAT" not in CACHEABLE_QUERY_TYPES
        assert "OFF_TOPIC" not in CACHEABLE_QUERY_TYPES

    async def test_general_cache_hit_returns_cached_response(self):
        """GENERAL query returns cached response on semantic hit."""
        state = make_initial_state(user_id=1, session_id="s1", query="уютная квартира с видом")
        state["query_type"] = "GENERAL"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.2] * 1024)
        cache.check_semantic = AsyncMock(return_value="Найдены подходящие варианты...")

        embeddings = AsyncMock()

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["cache_hit"] is True
        assert result["cached_response"] == "Найдены подходящие варианты..."
        cache.check_semantic.assert_awaited_once()


class TestCacheCheckEmbeddingError:
    """Test cache_check_node graceful fallback on embedding failure."""

    async def test_embedding_error_sets_error_state(self):
        """When embedding fails, sets embedding_error and user-friendly response."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)  # cache miss

        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(
            side_effect=httpx.RemoteProtocolError("Server disconnected")
        )

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["embedding_error"] is True
        assert result["embedding_error_type"] == "RemoteProtocolError"
        assert result["cache_hit"] is False
        assert "недоступен" in result["response"]
        assert result["query_embedding"] is None

    async def test_embedding_error_on_read_timeout(self):
        """ReadTimeout also triggers graceful fallback."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)

        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(side_effect=httpx.ReadTimeout("Read timed out"))

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["embedding_error"] is True
        assert result["cache_hit"] is False

    async def test_cached_embedding_skips_bge_call(self):
        """When embedding cache hits, no BGE-M3 call — no error possible."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "FAQ"

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
        cache.check_semantic = AsyncMock(return_value=None)

        embeddings = MagicMock()
        # aembed_hybrid should NOT be called
        embeddings.aembed_hybrid = AsyncMock(side_effect=Exception("should not be called"))

        result = await cache_check_node(state, cache=cache, embeddings=embeddings)

        assert result["embedding_error"] is False
        assert result["cache_hit"] is False
        embeddings.aembed_hybrid.assert_not_awaited()
