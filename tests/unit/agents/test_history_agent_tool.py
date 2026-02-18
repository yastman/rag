"""Tests for history_search tool wrapping sub-graph (#408)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.runnables import RunnableConfig


def _make_config(user_id: int = 123) -> RunnableConfig:
    return RunnableConfig(configurable={"user_id": user_id, "session_id": "s-1"})


async def test_history_tool_invokes_subgraph():
    """history_search tool invokes the sub-graph and returns summary."""
    with patch("telegram_bot.agents.history_graph.graph.build_history_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "summary": "Ранее вы спрашивали о ценах.",
                "results": [{"score": 0.9}],
                "results_relevant": True,
                "rewrite_count": 0,
                "latency_stages": {"retrieve": 0.1},
            }
        )
        mock_build.return_value = mock_graph

        from telegram_bot.agents.tools import create_history_search_tool

        svc = AsyncMock()
        llm = AsyncMock()
        tool = create_history_search_tool(history_service=svc, llm=llm)
        config = _make_config(user_id=42)

        result = await tool.ainvoke({"query": "цены"}, config=config)

        assert "Ранее вы спрашивали" in result
        mock_build.assert_called_once_with(history_service=svc, llm=llm)


async def test_history_tool_no_user_context():
    """Missing user_id returns error message."""
    from telegram_bot.agents.tools import create_history_search_tool

    svc = AsyncMock()
    tool = create_history_search_tool(history_service=svc)
    config = RunnableConfig(configurable={})

    result = await tool.ainvoke({"query": "test"}, config=config)

    assert "error" in result.lower() or "context" in result.lower()


async def test_history_tool_graph_failure():
    """Sub-graph failure returns controlled error."""
    with patch("telegram_bot.agents.history_graph.graph.build_history_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Graph failed"))
        mock_build.return_value = mock_graph

        from telegram_bot.agents.tools import create_history_search_tool

        svc = AsyncMock()
        tool = create_history_search_tool(history_service=svc)
        config = _make_config()

        result = await tool.ainvoke({"query": "test"}, config=config)

        assert isinstance(result, str)
        assert "ошибк" in result.lower() or "error" in result.lower()
