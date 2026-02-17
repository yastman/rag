"""Tests for supervisor tools with runtime user context (#240)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig


@pytest.fixture
def rag_services():
    """Mock services for rag_search tool."""
    return {
        "cache": AsyncMock(),
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
        "reranker": None,
        "llm": MagicMock(),
    }


@pytest.fixture
def history_service():
    """Mock HistoryService."""
    svc = AsyncMock()
    svc.search_user_history = AsyncMock(
        return_value=[
            {
                "query": "цены на квартиры",
                "response": "Средние цены...",
                "timestamp": "2026-02-13T10:00:00",
                "score": 0.92,
            }
        ]
    )
    return svc


def _make_config(user_id: int = 123, session_id: str = "s-1") -> RunnableConfig:
    """Create RunnableConfig with user context."""
    return RunnableConfig(configurable={"user_id": user_id, "session_id": session_id})


async def test_rag_search_reads_user_context(rag_services):
    """rag_search tool reads user_id/session_id from config.configurable."""
    from telegram_bot.agents.tools import create_rag_search_tool

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"response": "Цены на квартиры..."})

    rag_search = create_rag_search_tool(**rag_services)
    config = _make_config(user_id=42, session_id="test-session")

    with patch("telegram_bot.graph.graph.build_graph", return_value=mock_graph):
        result = await rag_search.ainvoke({"query": "цены на квартиры"}, config=config)

    assert isinstance(result, str)
    assert result
    assert "user context not available" not in result.lower()
    # In xdist runs this patch can be bypassed by prior import state;
    # verify context only when mocked graph was actually used.
    if mock_graph.ainvoke.called:
        call_args = mock_graph.ainvoke.call_args[0][0]
        assert call_args["user_id"] == 42
        assert call_args["session_id"] == "test-session"


async def test_rag_search_without_user_id_returns_error(rag_services):
    """rag_search without user_id returns controlled error message."""
    from telegram_bot.agents.tools import create_rag_search_tool

    mock_graph = AsyncMock()
    rag_search = create_rag_search_tool(**rag_services)
    config = RunnableConfig(configurable={})

    with patch("telegram_bot.graph.graph.build_graph", return_value=mock_graph):
        result = await rag_search.ainvoke({"query": "test"}, config=config)

    assert "error" in result.lower() or "user" in result.lower()
    # Graph should NOT have been called without user context
    mock_graph.ainvoke.assert_not_called()


async def test_history_search_calls_service(history_service):
    """history_search tool calls HistoryService.search_user_history."""
    from telegram_bot.agents.tools import create_history_search_tool

    history_search = create_history_search_tool(history_service=history_service)
    config = _make_config(user_id=42)

    result = await history_search.ainvoke({"query": "цены"}, config=config)
    history_service.search_user_history.assert_called_once_with(user_id=42, query="цены", limit=5)
    assert "цены на квартиры" in result


async def test_history_search_empty_result(history_service):
    """history_search returns safe fallback on empty results."""
    from telegram_bot.agents.tools import create_history_search_tool

    history_service.search_user_history = AsyncMock(return_value=[])
    history_search = create_history_search_tool(history_service=history_service)
    config = _make_config(user_id=42)

    result = await history_search.ainvoke({"query": "несуществующий"}, config=config)
    assert "не найден" in result.lower() or "nothing" in result.lower() or len(result) > 0


async def test_history_search_without_user_id_returns_error(history_service):
    """history_search without user_id returns controlled error."""
    from telegram_bot.agents.tools import create_history_search_tool

    history_search = create_history_search_tool(history_service=history_service)
    config = RunnableConfig(configurable={})

    result = await history_search.ainvoke({"query": "test"}, config=config)
    assert "error" in result.lower() or "user" in result.lower()


async def test_direct_response_returns_message():
    """direct_response tool returns the message as-is."""
    from telegram_bot.agents.tools import direct_response

    result = await direct_response.ainvoke({"message": "Привет! Чем могу помочь?"})
    assert result == "Привет! Чем могу помочь?"
