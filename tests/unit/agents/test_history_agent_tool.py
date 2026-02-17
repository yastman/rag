"""Tests for history agent tool (#240 Task 4)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from langchain_core.runnables import RunnableConfig


def _make_config(user_id: int = 123) -> RunnableConfig:
    return RunnableConfig(configurable={"user_id": user_id, "session_id": "s-1"})


async def test_history_agent_calls_search_user_history():
    """history_search calls HistoryService.search_user_history(user_id, query, limit=5)."""
    from telegram_bot.agents.history_agent import create_history_agent

    svc = AsyncMock()
    svc.search_user_history = AsyncMock(
        return_value=[
            {
                "query": "цены на квартиры",
                "response": "Средние цены в Варне...",
                "timestamp": "2026-02-13T10:00:00",
                "score": 0.92,
            }
        ]
    )
    tool = create_history_agent(history_service=svc)
    config = _make_config(user_id=42)

    result = await tool.ainvoke({"query": "цены"}, config=config)

    svc.search_user_history.assert_called_once_with(user_id=42, query="цены", limit=5)
    assert "цены на квартиры" in result


async def test_history_agent_empty_results_fallback():
    """Empty results return safe fallback message."""
    from telegram_bot.agents.history_agent import create_history_agent

    svc = AsyncMock()
    svc.search_user_history = AsyncMock(return_value=[])
    tool = create_history_agent(history_service=svc)
    config = _make_config(user_id=42)

    result = await tool.ainvoke({"query": "несуществующий"}, config=config)

    assert isinstance(result, str)
    assert len(result) > 0


async def test_history_agent_formats_multiple_results():
    """Multiple results are formatted with numbered entries."""
    from telegram_bot.agents.history_agent import create_history_agent

    svc = AsyncMock()
    svc.search_user_history = AsyncMock(
        return_value=[
            {
                "query": "цены",
                "response": "Средние цены...",
                "timestamp": "2026-02-13T10:00:00",
                "score": 0.9,
            },
            {
                "query": "районы",
                "response": "Лучшие районы...",
                "timestamp": "2026-02-12T15:00:00",
                "score": 0.85,
            },
        ]
    )
    tool = create_history_agent(history_service=svc)
    config = _make_config()

    result = await tool.ainvoke({"query": "цены"}, config=config)

    assert "1." in result
    assert "2." in result
    assert "цены" in result
    assert "районы" in result


async def test_history_agent_service_exception_returns_error():
    """Service exception returns controlled error, not traceback."""
    from telegram_bot.agents.history_agent import create_history_agent

    svc = AsyncMock()
    svc.search_user_history = AsyncMock(side_effect=RuntimeError("DB down"))
    tool = create_history_agent(history_service=svc)
    config = _make_config()

    result = await tool.ainvoke({"query": "test"}, config=config)

    assert isinstance(result, str)
    assert "ошибк" in result.lower() or "error" in result.lower()
