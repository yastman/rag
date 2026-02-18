"""Resilience tests for Kommo CRM fail-soft behavior (#389).

Verifies that CRM tools degrade gracefully when Kommo API is unavailable,
returning user-friendly messages instead of propagating exceptions.
"""

from unittest.mock import AsyncMock


async def test_crm_tool_fail_soft_on_kommo_error():
    """crm_create_deal should return friendly message on API errors."""
    from telegram_bot.agents.crm_tools import create_crm_tools

    kommo = AsyncMock()
    kommo._request_json = AsyncMock(side_effect=RuntimeError("429 Too Many Requests"))

    tools = create_crm_tools(kommo=kommo, history_service=AsyncMock(), llm=AsyncMock())
    create_deal = next(t for t in tools if t.name == "crm_create_deal")

    result = await create_deal.ainvoke({"name": "Lead", "pipeline_id": 1})
    assert "temporarily unavailable" in result.lower()


async def test_crm_upsert_contact_fail_soft():
    """crm_upsert_contact should return friendly message on API errors."""
    from telegram_bot.agents.crm_tools import create_crm_tools

    kommo = AsyncMock()
    kommo._request_json = AsyncMock(side_effect=ConnectionError("Network unreachable"))

    tools = create_crm_tools(kommo=kommo, history_service=AsyncMock(), llm=AsyncMock())
    upsert = next(t for t in tools if t.name == "crm_upsert_contact")

    result = await upsert.ainvoke({"phone": "+380501234567", "name": "Test"})
    assert "temporarily unavailable" in result.lower()


async def test_crm_deal_draft_fail_soft_no_history():
    """crm_generate_deal_draft should handle missing history gracefully."""
    from telegram_bot.agents.crm_tools import create_crm_tools

    tools = create_crm_tools(
        kommo=AsyncMock(),
        history_service=None,
        llm=AsyncMock(),
    )
    draft = next(t for t in tools if t.name == "crm_generate_deal_draft")

    result = await draft.ainvoke({"session_id": "test-session"})
    assert "unavailable" in result.lower()
