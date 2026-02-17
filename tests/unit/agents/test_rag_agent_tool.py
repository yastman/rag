"""Tests for RAG agent tool wrapper (#240 Task 3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.runnables import RunnableConfig


async def test_rag_agent_invokes_graph_and_returns_response():
    """RAG agent tool invokes build_graph().ainvoke() and returns response."""
    from telegram_bot.agents.rag_agent import create_rag_agent

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={"response": "Средняя цена квартиры — 85,000 EUR."})

    services = {
        "cache": AsyncMock(),
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
        "reranker": None,
        "llm": MagicMock(),
    }
    agent = create_rag_agent(**services)
    config = RunnableConfig(configurable={"user_id": 42, "session_id": "s-1"})

    with patch("telegram_bot.graph.graph.build_graph", return_value=mock_graph):
        result = await agent.ainvoke({"query": "цена квартиры"}, config=config)

    assert "85,000 EUR" in result
    call_state = mock_graph.ainvoke.call_args[0][0]
    assert call_state["user_id"] == 42
    assert call_state["session_id"] == "s-1"


async def test_rag_agent_missing_response_key():
    """RAG agent returns fallback when graph result has no response key."""
    from telegram_bot.agents.rag_agent import create_rag_agent

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={})

    services = {
        "cache": AsyncMock(),
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
    }
    agent = create_rag_agent(**services)
    config = RunnableConfig(configurable={"user_id": 1, "session_id": "s-1"})

    with patch("telegram_bot.graph.graph.build_graph", return_value=mock_graph):
        result = await agent.ainvoke({"query": "test"}, config=config)

    assert isinstance(result, str)
    assert len(result) > 0


async def test_rag_agent_graph_exception_returns_error():
    """RAG agent returns controlled error when graph raises exception."""
    from telegram_bot.agents.rag_agent import create_rag_agent

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Service down"))

    services = {
        "cache": AsyncMock(),
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
    }
    agent = create_rag_agent(**services)
    config = RunnableConfig(configurable={"user_id": 1, "session_id": "s-1"})

    with patch("telegram_bot.graph.graph.build_graph", return_value=mock_graph):
        result = await agent.ainvoke({"query": "test"}, config=config)

    assert "error" in result.lower() or "ошибк" in result.lower()
