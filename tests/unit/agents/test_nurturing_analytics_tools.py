"""Tests for role-gated nurturing + analytics tools (#390)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from langchain_core.tools import tool

from telegram_bot.agents.manager_tools import build_tools_for_role, create_manager_nurturing_tools


@tool
async def base_tool(message: str) -> str:
    """Base tool for role-selection tests."""
    return message


async def test_manager_tools_hidden_for_client_role():
    nurturing_tools = create_manager_nurturing_tools(
        analytics_service=AsyncMock(),
        nurturing_service=AsyncMock(),
    )
    client_tools = build_tools_for_role(
        role="client",
        base_tools=[base_tool],
        manager_tools=nurturing_tools,
    )
    manager_tools = build_tools_for_role(
        role="manager",
        base_tools=[base_tool],
        manager_tools=nurturing_tools,
    )

    client_names = {t.name for t in client_tools}
    manager_names = {t.name for t in manager_tools}

    assert "manager_get_funnel_analytics" not in client_names
    assert "manager_run_nurturing_batch" not in client_names
    assert "manager_get_funnel_analytics" in manager_names
    assert "manager_run_nurturing_batch" in manager_names


async def test_manager_get_funnel_analytics_returns_report():
    analytics_service = AsyncMock()
    analytics_service.get_latest_summary = AsyncMock(
        return_value=[{"stage": "inquiry", "rate": 0.4}]
    )
    tools = create_manager_nurturing_tools(
        analytics_service=analytics_service,
        nurturing_service=AsyncMock(),
    )
    analytics_tool = next(t for t in tools if t.name == "manager_get_funnel_analytics")

    config = {"configurable": {"role": "manager"}}
    result = await analytics_tool.ainvoke({"query": "show funnel"}, config=config)

    assert "inquiry" in result
    analytics_service.get_latest_summary.assert_called_once()


async def test_manager_get_funnel_analytics_denies_client():
    tools = create_manager_nurturing_tools(
        analytics_service=AsyncMock(),
        nurturing_service=AsyncMock(),
    )
    analytics_tool = next(t for t in tools if t.name == "manager_get_funnel_analytics")

    config = {"configurable": {"role": "client"}}
    result = await analytics_tool.ainvoke({"query": "show funnel"}, config=config)

    assert "Access denied" in result


async def test_manager_run_nurturing_batch_returns_count():
    nurturing_service = AsyncMock()
    nurturing_service.run_once = AsyncMock(return_value=15)
    tools = create_manager_nurturing_tools(
        analytics_service=AsyncMock(),
        nurturing_service=nurturing_service,
    )
    batch_tool = next(t for t in tools if t.name == "manager_run_nurturing_batch")

    config = {"configurable": {"role": "manager"}}
    result = await batch_tool.ainvoke({"query": "run now"}, config=config)

    assert "15" in result
    nurturing_service.run_once.assert_called_once()
