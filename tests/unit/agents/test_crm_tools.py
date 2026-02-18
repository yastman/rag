"""Tests for CRM supervisor tools (#389)."""

from unittest.mock import AsyncMock

from telegram_bot.agents.crm_tools import create_crm_tools


async def test_create_crm_tools_registers_expected_names():
    kommo = AsyncMock()
    history = AsyncMock()
    llm = AsyncMock()

    tools = create_crm_tools(kommo=kommo, history_service=history, llm=llm)
    names = {t.name for t in tools}

    assert "crm_generate_deal_draft" in names
    assert "crm_upsert_contact" in names
    assert "crm_create_deal" in names


async def test_create_crm_tools_returns_list():
    tools = create_crm_tools(kommo=AsyncMock(), history_service=AsyncMock(), llm=AsyncMock())
    assert isinstance(tools, list)
    assert len(tools) >= 3
