"""Tests for PipelineMetrics instrumentation in graph nodes (#436)."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.nodes.cache import cache_check_node
from telegram_bot.graph.nodes.generate import generate_node
from telegram_bot.graph.nodes.rerank import rerank_node
from telegram_bot.graph.nodes.retrieve import retrieve_node
from telegram_bot.graph.state import make_initial_state
from telegram_bot.services.metrics import PipelineMetrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Reset PipelineMetrics singleton before and after each test."""
    PipelineMetrics.reset()
    yield
    PipelineMetrics.reset()


@pytest.fixture(autouse=True)
def _ensure_redisvl_mock(monkeypatch):
    """Ensure redisvl modules are importable (mock if needed)."""
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


_OK_META = {"backend_error": False, "error_type": None, "error_message": None}


def _make_docs(n: int = 3) -> list[dict]:
    return [
        {"id": str(i), "text": f"Doc {i}", "score": 0.9 - i * 0.1, "metadata": {}} for i in range(n)
    ]


class TestRetrieveNodeMetrics:
    """retrieve_node records timing to PipelineMetrics."""

    async def test_cache_miss_records_retrieve_timing(self):
        """retrieve_node records 'retrieve' timing on Qdrant path."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["query_embedding"] = [0.1] * 1024

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(_make_docs(3), _OK_META))

        await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        stats = PipelineMetrics.get().get_stats()
        assert "retrieve" in stats["timings"], "Expected 'retrieve' timing to be recorded"
        assert stats["timings"]["retrieve"]["count"] == 1

    async def test_search_cache_hit_records_retrieve_timing(self):
        """retrieve_node records 'retrieve' timing even on search cache hit."""
        state = make_initial_state(user_id=1, session_id="s1", query="cached")
        state["query_embedding"] = [0.2] * 1024

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=_make_docs(2))

        qdrant = AsyncMock()
        sparse_embeddings = AsyncMock()

        await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        stats = PipelineMetrics.get().get_stats()
        assert "retrieve" in stats["timings"]
        assert stats["timings"]["retrieve"]["count"] == 1


class TestGenerateNodeMetrics:
    """generate_node records timing to PipelineMetrics."""

    async def test_records_generate_timing(self):
        """generate_node records 'generate' timing after LLM call."""
        from unittest.mock import patch

        state = make_initial_state(user_id=1, session_id="s1", query="Сколько стоит?")
        state["documents"] = _make_docs(2)
        state["query_type"] = "FAQ"
        state["retrieved_context"] = []

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Ответ на вопрос"
        mock_completion.model = "gpt-4o-mini"
        mock_completion.usage = None

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("telegram_bot.graph.nodes.generate._get_config") as mock_cfg:
            config = MagicMock()
            config.llm_model = "gpt-4o-mini"
            config.llm_temperature = 0.7
            config.generate_max_tokens = 1024
            config.domain = "недвижимость"
            config.streaming_enabled = False
            config.show_sources = False
            config.response_style_enabled = False
            config.response_style_shadow_mode = False
            config.create_llm.return_value = mock_llm
            mock_cfg.return_value = config

            with patch(
                "telegram_bot.graph.nodes.generate.get_prompt", return_value="Ты ассистент."
            ):
                await generate_node(state)

        stats = PipelineMetrics.get().get_stats()
        assert "generate" in stats["timings"], "Expected 'generate' timing to be recorded"
        assert stats["timings"]["generate"]["count"] == 1
        assert stats["timings"]["generate"]["last"] > 0


class TestRerankNodeMetrics:
    """rerank_node records timing to PipelineMetrics."""

    async def test_colbert_rerank_records_timing(self):
        """rerank_node records 'rerank' timing when ColBERT reranker is used."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs(5)

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(
            return_value=[
                {"index": 0, "score": 0.95},
                {"index": 2, "score": 0.82},
            ]
        )

        await rerank_node(state, reranker=reranker)

        stats = PipelineMetrics.get().get_stats()
        assert "rerank" in stats["timings"]
        assert stats["timings"]["rerank"]["count"] == 1

    async def test_fallback_sort_records_timing(self):
        """rerank_node records 'rerank' timing on score-based fallback (no reranker)."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs(5)

        await rerank_node(state, reranker=None)

        stats = PipelineMetrics.get().get_stats()
        assert "rerank" in stats["timings"]
        assert stats["timings"]["rerank"]["count"] == 1

    async def test_empty_documents_records_timing(self):
        """rerank_node records 'rerank' timing even when no documents."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = []

        await rerank_node(state, reranker=None)

        stats = PipelineMetrics.get().get_stats()
        assert "rerank" in stats["timings"]
        assert stats["timings"]["rerank"]["count"] == 1


class TestCacheCheckNodeMetrics:
    """cache_check_node increments hit/miss counters in PipelineMetrics."""

    async def test_cache_hit_increments_cache_hit_counter(self):
        """cache_check_node increments 'cache_hit' counter on semantic hit."""
        state = make_initial_state(user_id=1, session_id="s1", query="FAQ about prices")
        state["query_type"] = "FAQ"

        embedding = [0.1] * 1024

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=embedding)
        cache.check_semantic = AsyncMock(return_value="Кешированный ответ")

        embeddings = AsyncMock()

        await cache_check_node(state, cache=cache, embeddings=embeddings)

        stats = PipelineMetrics.get().get_stats()
        assert stats["counters"].get("cache_hit", 0) == 1
        assert stats["counters"].get("cache_miss", 0) == 0

    async def test_cache_miss_increments_cache_miss_counter(self):
        """cache_check_node increments 'cache_miss' counter on semantic miss."""
        state = make_initial_state(user_id=1, session_id="s1", query="new question")
        state["query_type"] = "FAQ"

        embedding = [0.2] * 1024

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=embedding)
        cache.check_semantic = AsyncMock(return_value=None)  # cache miss

        embeddings = AsyncMock()

        await cache_check_node(state, cache=cache, embeddings=embeddings)

        stats = PipelineMetrics.get().get_stats()
        assert stats["counters"].get("cache_miss", 0) == 1
        assert stats["counters"].get("cache_hit", 0) == 0

    async def test_general_query_type_always_misses(self):
        """GENERAL query type bypasses semantic cache — always increments cache_miss."""
        state = make_initial_state(user_id=1, session_id="s1", query="general question")
        state["query_type"] = "GENERAL"  # not in CACHEABLE_QUERY_TYPES

        embedding = [0.3] * 1024

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=embedding)
        cache.check_semantic = AsyncMock(return_value=None)

        embeddings = AsyncMock()

        await cache_check_node(state, cache=cache, embeddings=embeddings)

        stats = PipelineMetrics.get().get_stats()
        assert stats["counters"].get("cache_miss", 0) == 1
        assert stats["counters"].get("cache_hit", 0) == 0
