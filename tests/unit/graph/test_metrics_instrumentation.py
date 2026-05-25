"""Tests for pipeline metrics instrumentation in graph nodes (#436, #2058).

Migrated from rolling-window assertions to SDK-native Prometheus
Histogram/Counter assertions. The legacy ``PipelineMetrics.get_stats()``
surface was removed in #2058; the canonical observability surface is
now ``pipeline_latency_seconds`` (Histogram, ``stage`` label) and
``rag_pipeline_events_total`` (Counter, ``event`` label).
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.runtime import Runtime
from prometheus_client import REGISTRY

from telegram_bot.graph.nodes.cache import cache_check_node
from telegram_bot.graph.nodes.generate import generate_node
from telegram_bot.graph.nodes.rerank import rerank_node
from telegram_bot.graph.nodes.retrieve import retrieve_node
from telegram_bot.graph.state import make_initial_state
from telegram_bot.services.metrics import (
    PipelineMetrics,
    pipeline_latency_seconds,
    rag_pipeline_events_total,
)


def _rt(**ctx) -> Runtime:
    return Runtime(context=ctx)


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Clear SDK Histogram + Counter children and the facade singleton.

    The Prometheus collectors are module-level (registered exactly once
    with the default REGISTRY); we only drop per-label children so each
    test starts from zero counts.
    """
    pipeline_latency_seconds.clear()
    rag_pipeline_events_total.clear()
    PipelineMetrics.reset()
    yield
    pipeline_latency_seconds.clear()
    rag_pipeline_events_total.clear()
    PipelineMetrics.reset()


def _stage_count(stage: str) -> int:
    """Read the observation count for ``stage`` directly from the registry."""
    sample = REGISTRY.get_sample_value("pipeline_latency_seconds_count", labels={"stage": stage})
    return int(sample or 0)


def _stage_sum(stage: str) -> float:
    """Read the observation sum (seconds) for ``stage`` from the registry."""
    sample = REGISTRY.get_sample_value("pipeline_latency_seconds_sum", labels={"stage": stage})
    return float(sample or 0.0)


def _event_count(event: str) -> int:
    """Read the cumulative count for ``event`` from the SDK Counter."""
    sample = REGISTRY.get_sample_value("rag_pipeline_events_total", labels={"event": event})
    return int(sample or 0)


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
    """retrieve_node observes 'retrieve' latency to pipeline_latency_seconds."""

    async def test_cache_miss_records_retrieve_timing(self):
        """retrieve_node observes a 'retrieve' latency on Qdrant path."""
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
            _rt(cache=cache, sparse_embeddings=sparse_embeddings, qdrant=qdrant),
        )

        assert _stage_count("retrieve") == 1, "Expected one 'retrieve' observation"

    async def test_search_cache_hit_records_retrieve_timing(self):
        """retrieve_node observes a 'retrieve' latency even on search-cache hit."""
        state = make_initial_state(user_id=1, session_id="s1", query="cached")
        state["query_embedding"] = [0.2] * 1024

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=_make_docs(2))

        qdrant = AsyncMock()
        sparse_embeddings = AsyncMock()

        await retrieve_node(
            state,
            _rt(cache=cache, sparse_embeddings=sparse_embeddings, qdrant=qdrant),
        )

        assert _stage_count("retrieve") == 1


class TestGenerateNodeMetrics:
    """generate_node observes 'generate' latency to pipeline_latency_seconds."""

    async def test_records_generate_timing(self):
        """generate_node observes a positive 'generate' latency after the LLM call."""
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

        assert _stage_count("generate") == 1, "Expected one 'generate' observation"
        assert _stage_sum("generate") > 0, "Observed latency should be positive"


class TestRerankNodeMetrics:
    """rerank_node observes 'rerank' latency to pipeline_latency_seconds."""

    async def test_colbert_rerank_records_timing(self):
        """rerank_node observes a 'rerank' latency when ColBERT reranker is used."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs(5)

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(
            return_value=[
                {"index": 0, "score": 0.95},
                {"index": 2, "score": 0.82},
            ]
        )

        await rerank_node(state, _rt(reranker=reranker))

        assert _stage_count("rerank") == 1

    async def test_fallback_sort_records_timing(self):
        """rerank_node observes a 'rerank' latency on score-based fallback."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs(5)

        await rerank_node(state, _rt())

        assert _stage_count("rerank") == 1

    async def test_empty_documents_records_timing(self):
        """rerank_node observes a 'rerank' latency even when no documents."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = []

        await rerank_node(state, _rt())

        assert _stage_count("rerank") == 1


class TestCacheCheckNodeMetrics:
    """cache_check_node increments hit/miss events on rag_pipeline_events_total."""

    async def test_cache_hit_increments_cache_hit_counter(self):
        """cache_check_node increments 'cache_hit' on semantic hit."""
        state = make_initial_state(user_id=1, session_id="s1", query="FAQ about prices")
        state["query_type"] = "FAQ"

        embedding = [0.1] * 1024

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=embedding)
        cache.check_semantic = AsyncMock(return_value="Кешированный ответ")

        embeddings = AsyncMock()

        await cache_check_node(state, _rt(cache=cache, embeddings=embeddings))

        assert _event_count("cache_hit") == 1
        assert _event_count("cache_miss") == 0

    async def test_cache_miss_increments_cache_miss_counter(self):
        """cache_check_node increments 'cache_miss' on semantic miss."""
        state = make_initial_state(user_id=1, session_id="s1", query="new question")
        state["query_type"] = "FAQ"

        embedding = [0.2] * 1024

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=embedding)
        cache.check_semantic = AsyncMock(return_value=None)  # cache miss

        embeddings = AsyncMock()

        await cache_check_node(state, _rt(cache=cache, embeddings=embeddings))

        assert _event_count("cache_miss") == 1
        assert _event_count("cache_hit") == 0

    async def test_general_query_type_misses_when_no_cached_response(self):
        """GENERAL query type checks semantic cache and increments cache_miss on MISS (#477)."""
        state = make_initial_state(user_id=1, session_id="s1", query="general question")
        state["query_type"] = "GENERAL"  # now in CACHEABLE_QUERY_TYPES (threshold 0.08)

        embedding = [0.3] * 1024

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=embedding)
        cache.check_semantic = AsyncMock(return_value=None)

        embeddings = AsyncMock()

        await cache_check_node(state, _rt(cache=cache, embeddings=embeddings))

        assert _event_count("cache_miss") == 1
        assert _event_count("cache_hit") == 0
