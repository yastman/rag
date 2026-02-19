"""Tests for rag_search tool with config-based context DI (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig


@pytest.fixture
def bot_context():
    """Create a mock BotContext for testing."""
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


async def test_rag_search_calls_build_graph(bot_context):
    """rag_search wraps existing LangGraph pipeline via build_graph."""
    from telegram_bot.agents.rag_tool import rag_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"response": "Цены от 50K EUR"})

    with patch("telegram_bot.agents.rag_tool.build_graph", return_value=mock_graph):
        result = await rag_search.ainvoke(
            {"query": "цены на квартиры"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert "50K" in result


async def test_rag_search_returns_fallback_on_empty(bot_context):
    """rag_search returns fallback when pipeline returns empty response."""
    from telegram_bot.agents.rag_tool import rag_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"response": ""})

    with patch("telegram_bot.agents.rag_tool.build_graph", return_value=mock_graph):
        result = await rag_search.ainvoke(
            {"query": "test"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert len(result) > 0


async def test_rag_search_handles_exception(bot_context):
    """rag_search returns error message when pipeline raises."""
    from telegram_bot.agents.rag_tool import rag_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Qdrant down"))

    with patch("telegram_bot.agents.rag_tool.build_graph", return_value=mock_graph):
        result = await rag_search.ainvoke(
            {"query": "test"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert "ошибк" in result.lower() or "error" in result.lower()


async def test_rag_search_stores_result_in_side_channel(bot_context):
    """rag_search stores full pipeline result in config's rag_result_store (#426)."""
    from telegram_bot.agents.rag_tool import rag_search

    full_result = {
        "response": "Ответ про квартиры.",
        "query_type": "FAQ",
        "documents": [{"metadata": {"title": "Doc1"}, "score": 0.85}],
        "cache_hit": False,
        "search_results_count": 3,
        "latency_stages": {"classify": 0.001, "generate": 0.5},
    }
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value=full_result)

    rag_result_store: dict = {}
    config = RunnableConfig(
        configurable={"bot_context": bot_context, "rag_result_store": rag_result_store}
    )

    with patch("telegram_bot.agents.rag_tool.build_graph", return_value=mock_graph):
        await rag_search.ainvoke({"query": "квартиры"}, config=config)

    assert rag_result_store.get("query_type") == "FAQ"
    assert len(rag_result_store.get("documents", [])) == 1
    assert "response" in rag_result_store


async def test_rag_search_writes_langfuse_scores(bot_context):
    """rag_search tool calls write_langfuse_scores with full pipeline result (#425)."""
    from telegram_bot.agents.rag_tool import rag_search

    full_result = {
        "response": "Ответ.",
        "query_type": "FAQ",
        "cache_hit": True,
        "latency_stages": {"classify": 0.001, "cache_check": 0.02},
        "search_results_count": 0,
    }
    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value=full_result)

    config = _make_config(bot_context)

    with (
        patch("telegram_bot.agents.rag_tool.build_graph", return_value=mock_graph),
        patch("telegram_bot.agents.rag_tool.write_langfuse_scores") as mock_write_scores,
    ):
        await rag_search.ainvoke({"query": "тест"}, config=config)

    mock_write_scores.assert_called_once()
    call_args = mock_write_scores.call_args
    result_dict = call_args[0][1]  # second positional arg
    assert result_dict["pipeline_wall_ms"] > 0
    assert "user_perceived_wall_ms" in result_dict
    assert "checkpointer_overhead_proxy_ms" in result_dict
