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
