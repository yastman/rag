"""Tests for manager role-based tool registry (#388)."""

from unittest.mock import AsyncMock

from langchain_core.tools import tool

from telegram_bot.agents.manager_tools import create_manager_tools
from telegram_bot.agents.tools import build_tools_for_role


@tool
async def base_tool(message: str) -> str:
    """Base tool for role-selection tests."""
    return message


async def test_manager_role_gets_manager_tools():
    manager_tools = create_manager_tools(lead_service=AsyncMock())
    tools = build_tools_for_role(
        role="manager",
        base_tools=[base_tool],
        manager_tools=manager_tools,
    )
    names = {t.name for t in tools}
    assert "manager_list_hot_leads" in names
    assert "manager_ack_hot_lead" in names


async def test_client_role_does_not_get_manager_tools():
    manager_tools = create_manager_tools(lead_service=AsyncMock())
    tools = build_tools_for_role(
        role="client",
        base_tools=[base_tool],
        manager_tools=manager_tools,
    )
    names = {t.name for t in tools}
    assert "manager_list_hot_leads" not in names
