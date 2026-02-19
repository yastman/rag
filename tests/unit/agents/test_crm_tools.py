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
    kommo.get_contacts = AsyncMock(
        return_value=[
            Contact(id=10, first_name="Ivan", last_name="Petrov"),
            Contact(id=11, first_name="Anna", last_name="Sidorova"),
        ]
    )
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


# --- Task 1: Happy path tests for 5 untested tools ---


async def test_crm_update_lead(bot_context, mock_kommo):
    """crm_update_lead calls KommoClient.update_lead with correct LeadUpdate."""
    from telegram_bot.agents.crm_tools import crm_update_lead

    result = await crm_update_lead.ainvoke(
        {"deal_id": 1, "name": "Updated Deal", "budget": 75000},
        config=_make_config(bot_context),
    )
    assert "обновлена" in result.lower()
    assert "1" in result
    mock_kommo.update_lead.assert_called_once()
    args = mock_kommo.update_lead.call_args
    assert args[0][0] == 1  # deal_id
    lead_update = args[0][1]
    assert lead_update.name == "Updated Deal"
    assert lead_update.budget == 75000


async def test_crm_upsert_contact(bot_context, mock_kommo):
    """crm_upsert_contact calls KommoClient.upsert_contact with phone + ContactCreate."""
    from telegram_bot.agents.crm_tools import crm_upsert_contact

    result = await crm_upsert_contact.ainvoke(
        {"phone": "+380501234567", "first_name": "Ivan", "last_name": "Petrov"},
        config=_make_config(bot_context),
    )
    assert "Контакт" in result
    assert "10" in result
    mock_kommo.upsert_contact.assert_called_once()
    args = mock_kommo.upsert_contact.call_args
    assert args[0][0] == "+380501234567"
    contact_create = args[0][1]
    assert contact_create.first_name == "Ivan"
    assert contact_create.last_name == "Petrov"


async def test_crm_create_task(bot_context, mock_kommo):
    """crm_create_task calls KommoClient.create_task with TaskCreate."""
    from telegram_bot.agents.crm_tools import crm_create_task

    result = await crm_create_task.ainvoke(
        {"text": "Follow up", "entity_id": 1, "complete_till": 1700000000},
        config=_make_config(bot_context),
    )
    assert "Задача создана" in result
    assert "200" in result
    mock_kommo.create_task.assert_called_once()
    task_create = mock_kommo.create_task.call_args[0][0]
    assert task_create.text == "Follow up"
    assert task_create.entity_id == 1
    assert task_create.complete_till == 1700000000


async def test_crm_link_contact_to_deal(bot_context, mock_kommo):
    """crm_link_contact_to_deal calls KommoClient.link_contact_to_lead."""
    from telegram_bot.agents.crm_tools import crm_link_contact_to_deal

    result = await crm_link_contact_to_deal.ainvoke(
        {"lead_id": 1, "contact_id": 10},
        config=_make_config(bot_context),
    )
    assert "привязан" in result.lower()
    assert "10" in result
    assert "1" in result
    mock_kommo.link_contact_to_lead.assert_called_once_with(1, 10)


async def test_crm_get_contacts(bot_context, mock_kommo):
    """crm_get_contacts returns formatted contact list."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    result = await crm_get_contacts.ainvoke(
        {"query": "Ivan"},
        config=_make_config(bot_context),
    )
    assert "Ivan" in result
    assert "Petrov" in result
    assert "ID: 10" in result
    assert "Anna" in result
    mock_kommo.get_contacts.assert_called_once_with("Ivan")


async def test_crm_get_contacts_empty(bot_context, mock_kommo):
    """crm_get_contacts returns 'not found' when no contacts match."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    mock_kommo.get_contacts.return_value = []
    result = await crm_get_contacts.ainvoke(
        {"query": "Nobody"},
        config=_make_config(bot_context),
    )
    assert "не найдены" in result.lower()


# --- Task 2: Error path tests ---


async def test_crm_get_deal_error(bot_context, mock_kommo):
    """crm_get_deal returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    mock_kommo.get_lead.side_effect = RuntimeError("API error")
    result = await crm_get_deal.ainvoke(
        {"deal_id": 1},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_create_lead_error(bot_context, mock_kommo):
    """crm_create_lead returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_create_lead

    mock_kommo.create_lead.side_effect = RuntimeError("API error")
    result = await crm_create_lead.ainvoke(
        {"name": "Fail Lead"},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_update_lead_error(bot_context, mock_kommo):
    """crm_update_lead returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_update_lead

    mock_kommo.update_lead.side_effect = RuntimeError("API error")
    result = await crm_update_lead.ainvoke(
        {"deal_id": 1, "name": "Fail"},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_upsert_contact_error(bot_context, mock_kommo):
    """crm_upsert_contact returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_upsert_contact

    mock_kommo.upsert_contact.side_effect = RuntimeError("API error")
    result = await crm_upsert_contact.ainvoke(
        {"phone": "+380501234567", "first_name": "Ivan"},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_add_note_error(bot_context, mock_kommo):
    """crm_add_note returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_add_note

    mock_kommo.add_note.side_effect = RuntimeError("API error")
    result = await crm_add_note.ainvoke(
        {"entity_type": "leads", "entity_id": 1, "text": "Note"},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_create_task_error(bot_context, mock_kommo):
    """crm_create_task returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_create_task

    mock_kommo.create_task.side_effect = RuntimeError("API error")
    result = await crm_create_task.ainvoke(
        {"text": "Task", "entity_id": 1, "complete_till": 1700000000},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_link_contact_to_deal_error(bot_context, mock_kommo):
    """crm_link_contact_to_deal returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_link_contact_to_deal

    mock_kommo.link_contact_to_lead.side_effect = RuntimeError("API error")
    result = await crm_link_contact_to_deal.ainvoke(
        {"lead_id": 1, "contact_id": 10},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_get_contacts_error(bot_context, mock_kommo):
    """crm_get_contacts returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    mock_kommo.get_contacts.side_effect = RuntimeError("API error")
    result = await crm_get_contacts.ainvoke(
        {"query": "Ivan"},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


# --- Task 3: Edge case tests ---


async def test_crm_tool_no_bot_context():
    """CRM tools return _CRM_UNAVAILABLE when bot_context key is missing."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    config = RunnableConfig(configurable={})
    result = await crm_get_deal.ainvoke({"deal_id": 1}, config=config)
    assert "недоступен" in result.lower()


async def test_crm_get_contacts_truncation(bot_context, mock_kommo):
    """crm_get_contacts shows only first 10 contacts when more are returned."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    mock_kommo.get_contacts.return_value = [
        Contact(id=i, first_name=f"User{i}", last_name=f"Last{i}") for i in range(15)
    ]
    result = await crm_get_contacts.ainvoke(
        {"query": "User"},
        config=_make_config(bot_context),
    )
    lines = [line for line in result.split("\n") if line.strip().startswith("-")]
    assert len(lines) == 10
    assert "User0" in result
    assert "User9" in result
    assert "User10" not in result
