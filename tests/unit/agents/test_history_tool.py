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
    """history_search delegates to history sub-graph."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"summary": "Вы спрашивали о ценах на квартиры"})

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

    with patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph):
        result = await history_search.ainvoke(
            {"query": "test"},
            config=_make_config(bot_context),
        )

    assert isinstance(result, str)
    assert "ошибк" in result.lower() or "error" in result.lower()


async def test_history_search_passes_threshold_to_graph(bot_context):
    """history_search passes history_relevance_threshold from BotContext to build_history_graph (#433)."""
    from telegram_bot.agents.history_tool import history_search

    bot_context.history_relevance_threshold = 0.5

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"summary": "test"})

    with patch(
        "telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph
    ) as mock_build:
        await history_search.ainvoke(
            {"query": "test"},
            config=_make_config(bot_context),
        )

    mock_build.assert_called_once()
    _, kwargs = mock_build.call_args
    assert kwargs.get("relevance_threshold") == 0.5


async def test_history_search_sets_reply_markup_on_success(bot_context):
    """history_search stores feedback keyboard in ctx.history_reply_markup on success (#434)."""
    from aiogram.types import InlineKeyboardMarkup

    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"summary": "Вы спрашивали о ценах"})

    with (
        patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph),
        patch("telegram_bot.agents.history_tool.get_client") as mock_get_client,
    ):
        mock_lf = MagicMock()
        mock_lf.get_current_trace_id.return_value = "trace-abc-123"
        mock_lf.update_current_span = MagicMock()
        mock_get_client.return_value = mock_lf

        await history_search.ainvoke(
            {"query": "цены"},
            config=_make_config(bot_context),
        )

    assert bot_context.history_reply_markup is not None
    assert isinstance(bot_context.history_reply_markup, InlineKeyboardMarkup)


async def test_history_search_no_reply_markup_on_empty_summary(bot_context):
    """history_search does not set reply_markup when summary is empty (#434)."""
    from telegram_bot.agents.history_tool import history_search

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"summary": ""})

    with (
        patch("telegram_bot.agents.history_tool.build_history_graph", return_value=mock_graph),
        patch("telegram_bot.agents.history_tool.get_client") as mock_get_client,
    ):
        mock_lf = MagicMock()
        mock_lf.get_current_trace_id.return_value = "trace-abc-123"
        mock_lf.update_current_span = MagicMock()
        mock_get_client.return_value = mock_lf

        await history_search.ainvoke(
            {"query": "несуществующий"},
            config=_make_config(bot_context),
        )

    # No summary → no keyboard
    assert bot_context.history_reply_markup is None
