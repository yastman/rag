"""Tests for CRM tools with config-based context DI (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from telegram_bot.agents.context import BotContext
from telegram_bot.services.kommo_models import Contact, Lead, Note, Task


@pytest.fixture
def mock_kommo():
    """Mock KommoClient."""
    kommo = AsyncMock()
    kommo.get_lead = AsyncMock(return_value=Lead(id=1, name="Test", budget=50000))
    kommo.create_lead = AsyncMock(return_value=Lead(id=2, name="New"))
    kommo.update_lead = AsyncMock(return_value=Lead(id=1, name="Updated"))
    kommo.upsert_contact = AsyncMock(return_value=Contact(id=10, first_name="Ivan"))
    kommo.add_note = AsyncMock(return_value=Note(id=100, text="Note"))
    kommo.create_task = AsyncMock(return_value=Task(id=200, text="Task"))
    kommo.link_contact_to_lead = AsyncMock()
    return kommo


@pytest.fixture
def bot_context(mock_kommo):
    """BotContext with mock KommoClient."""
    return BotContext(
        telegram_user_id=42,
        session_id="s-1",
        language="ru",
        kommo_client=mock_kommo,
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


async def test_crm_get_deal(bot_context):
    """crm_get_deal returns lead data."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    result = await crm_get_deal.ainvoke(
        {"deal_id": 1},
        config=_make_config(bot_context),
    )
    assert "Test" in result or "50000" in result


async def test_crm_create_lead(bot_context):
    """crm_create_lead calls KommoClient.create_lead."""
    from telegram_bot.agents.crm_tools import crm_create_lead

    result = await crm_create_lead.ainvoke(
        {"name": "New Lead", "budget": 100000},
        config=_make_config(bot_context),
    )
    assert isinstance(result, str)
    bot_context.kommo_client.create_lead.assert_called_once()


async def test_crm_add_note(bot_context):
    """crm_add_note calls KommoClient.add_note."""
    from telegram_bot.agents.crm_tools import crm_add_note

    result = await crm_add_note.ainvoke(
        {"entity_type": "leads", "entity_id": 1, "text": "Important note"},
        config=_make_config(bot_context),
    )
    assert isinstance(result, str)
    bot_context.kommo_client.add_note.assert_called_once()


async def test_crm_tool_without_kommo_returns_error():
    """CRM tools return error when kommo_client is None."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    ctx = BotContext(
        telegram_user_id=42,
        session_id="s-1",
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

    result = await crm_get_deal.ainvoke(
        {"deal_id": 1},
        config=_make_config(ctx),
    )
    assert "недоступн" in result.lower() or "crm" in result.lower()
