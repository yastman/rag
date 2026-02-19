"""Tests for history_search tool with config-based context DI (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig


@pytest.fixture
def bot_context():
    """Mock BotContext with history_service."""
    from telegram_bot.agents.context import BotContext

    return BotContext(
        telegram_user_id=42,
        session_id="test-session",
        language="ru",
        kommo_client=None,
        history_service=AsyncMock(),
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )


def _make_config(bot_context) -> RunnableConfig:
    return RunnableConfig(configurable={"bot_context": bot_context})


async def test_history_search_calls_graph(bot_context):
    """history_search delegates to history sub-graph on cache miss."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"summary": "Вы спрашивали о ценах на квартиры"})
    bot_context.cache.get_embedding = AsyncMock(return_value=[0.1] * 10)
    bot_context.cache.check_semantic = AsyncMock(return_value=None)

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "цены"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert len(result) > 0


async def test_history_search_empty_result(bot_context):
    """history_search returns fallback on empty summary."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"summary": ""})
    bot_context.cache.get_embedding = AsyncMock(return_value=[0.1] * 10)
    bot_context.cache.check_semantic = AsyncMock(return_value=None)

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "несуществующий"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert len(result) > 0


async def test_history_search_exception_returns_error(bot_context):
    """history_search returns error on exception."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Qdrant down"))
    bot_context.cache.get_embedding = AsyncMock(return_value=[0.1] * 10)
    bot_context.cache.check_semantic = AsyncMock(return_value=None)

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "test"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert "ошибк" in result.lower() or "error" in result.lower()


# --- Semantic cache tests (#431/#464) ---


async def test_history_search_semantic_cache_hit(bot_context):
    """Semantic cache hit returns cached summary without calling graph."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    bot_context.cache.get_embedding = AsyncMock(return_value=[0.1] * 10)
    bot_context.cache.check_semantic = AsyncMock(return_value="Кешированный ответ о ценах")

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "цены"},
            config=_make_config(bot_context),
        )

    assert result == "Кешированный ответ о ценах"
    mock_graph.ainvoke.assert_not_called()
    bot_context.cache.check_semantic.assert_called_once()


async def test_history_search_semantic_cache_miss_calls_graph_and_stores(bot_context):
    """Cache miss: graph is invoked and result stored in semantic cache."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "summary": "Вы спрашивали о ценах",
            "results": [],
            "results_relevant": True,
            "rewrite_count": 0,
            "latency_stages": {},
        }
    )
    bot_context.cache.get_embedding = AsyncMock(return_value=[0.1] * 10)
    bot_context.cache.check_semantic = AsyncMock(return_value=None)
    bot_context.cache.store_semantic = AsyncMock()

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "цены"},
            config=_make_config(bot_context),
        )

    assert result == "Вы спрашивали о ценах"
    mock_graph.ainvoke.assert_called_once()
    bot_context.cache.store_semantic.assert_called_once()
    # Stored with ENTITY type
    call_kwargs = bot_context.cache.store_semantic.call_args
    assert call_kwargs.args[0] == "цены"
    assert call_kwargs.kwargs["query_type"] == "ENTITY"


async def test_history_search_embedding_computed_on_cache_miss(bot_context):
    """Embedding is computed and stored when not in cache."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "summary": "Ответ из графа",
            "results": [],
            "results_relevant": True,
            "rewrite_count": 0,
            "latency_stages": {},
        }
    )
    # Embedding not cached — force computation
    bot_context.cache.get_embedding = AsyncMock(return_value=None)
    bot_context.cache.check_semantic = AsyncMock(return_value=None)
    bot_context.cache.store_embedding = AsyncMock()
    bot_context.cache.store_semantic = AsyncMock()
    bot_context.embeddings.aembed_hybrid = AsyncMock(return_value=([0.5] * 10, {}))

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "квартиры"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    # Embedding stored after computation
    bot_context.cache.store_embedding.assert_called_once()
    # Summary also stored for future hits
    bot_context.cache.store_semantic.assert_called_once()
