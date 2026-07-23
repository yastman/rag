"""Tests for CRM tools with config-based context DI (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.agents.context import BotContext
from telegram_bot.agents.tooling import RunnableConfig
from telegram_bot.services.crm.kommo_models import Contact, Lead, Note, Task


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
    kommo.search_leads = AsyncMock(
        return_value=[
            Lead(id=20, name="Deal Alpha", budget=100000),
            Lead(id=21, name="Deal Beta"),
        ]
    )
    kommo.get_tasks = AsyncMock(
        return_value=[
            Task(id=300, text="Call back client", complete_till=9999999999, is_completed=False),
            Task(id=301, text="Send docs", complete_till=1000000000, is_completed=False),
        ]
    )
    kommo.update_contact = AsyncMock(return_value=Contact(id=50, first_name="Updated"))
    return kommo


@pytest.fixture
def bot_context(mock_kommo):
    """BotContext with mock KommoClient (set as dynamic attribute)."""
    ctx = BotContext(
        telegram_user_id=42,
        session_id="s-1",
        language="ru",
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    ctx.kommo_client = mock_kommo
    ctx.manager_id = 42
    return ctx


@pytest.fixture
def bot_context_no_manager(mock_kommo):
    """BotContext without manager_ids set."""
    ctx = BotContext(
        telegram_user_id=42,
        session_id="s-1",
        language="ru",
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    ctx.kommo_client = mock_kommo
    return ctx


def _make_config(bot_context) -> RunnableConfig:
    return RunnableConfig(configurable={"bot_context": bot_context})


async def test_crm_get_deal(bot_context):
    """crm_get_deal returns lead data."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    result = await crm_get_deal.ainvoke({"deal_id": 1}, config=_make_config(bot_context))
    assert "Test" in result or "50000" in result


async def test_crm_create_lead(bot_context):
    """crm_create_lead calls KommoClient.create_lead."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_create_lead

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_create_lead.ainvoke(
            {"name": "New Lead", "budget": 100000}, config=_make_config(bot_context)
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
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
        content_filter_enabled=True,
        guard_mode="hard",
    )
    ctx.kommo_client = None

    result = await crm_get_deal.ainvoke({"deal_id": 1}, config=_make_config(ctx))
    assert "недоступн" in result.lower() or "crm" in result.lower()


# --- Task 1: Happy path tests for 5 untested tools ---


async def test_crm_update_lead(bot_context, mock_kommo):
    """crm_update_lead calls KommoClient.update_lead with correct LeadUpdate."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_update_lead

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
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
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_upsert_contact

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
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
        {"lead_id": 1, "contact_id": 10}, config=_make_config(bot_context)
    )
    assert "привязан" in result.lower()
    assert "10" in result
    assert "1" in result
    mock_kommo.link_contact_to_lead.assert_called_once_with(1, 10)


async def test_crm_get_contacts(bot_context, mock_kommo):
    """crm_get_contacts returns formatted contact list."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    result = await crm_get_contacts.ainvoke({"query": "Ivan"}, config=_make_config(bot_context))
    assert "Ivan" in result
    assert "Petrov" in result
    assert "ID: 10" in result
    assert "Anna" in result
    mock_kommo.get_contacts.assert_called_once_with("Ivan")


async def test_crm_get_contacts_empty(bot_context, mock_kommo):
    """crm_get_contacts returns 'not found' when no contacts match."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    mock_kommo.get_contacts.return_value = []
    result = await crm_get_contacts.ainvoke({"query": "Nobody"}, config=_make_config(bot_context))
    assert "не найдены" in result.lower()


# --- Task 2: Error path tests ---


async def test_crm_get_deal_error(bot_context, mock_kommo):
    """crm_get_deal returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    mock_kommo.get_lead.side_effect = RuntimeError("API error")
    result = await crm_get_deal.ainvoke({"deal_id": 1}, config=_make_config(bot_context))
    assert "Ошибка" in result


async def test_crm_create_lead_error(bot_context, mock_kommo):
    """crm_create_lead returns error string on exception."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_create_lead

    mock_kommo.create_lead.side_effect = RuntimeError("API error")
    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_create_lead.ainvoke(
            {"name": "Error Lead", "budget": 50000}, config=_make_config(bot_context)
        )
    assert "Ошибка" in result


async def test_crm_update_lead_error(bot_context, mock_kommo):
    """crm_update_lead returns error string on exception."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_update_lead

    mock_kommo.update_lead.side_effect = RuntimeError("API error")
    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_update_lead.ainvoke(
            {"deal_id": 1, "name": "Fail"}, config=_make_config(bot_context)
        )
    assert "Ошибка" in result


async def test_crm_upsert_contact_error(bot_context, mock_kommo):
    """crm_upsert_contact returns error string on exception."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_upsert_contact

    mock_kommo.upsert_contact.side_effect = RuntimeError("API error")
    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_upsert_contact.ainvoke(
            {"phone": "+123", "first_name": "Test", "last_name": "User"},
            config=_make_config(bot_context),
        )
    assert "Ошибка" in result


async def test_crm_add_note_error(bot_context, mock_kommo):
    """crm_add_note returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_add_note

    mock_kommo.add_note.side_effect = RuntimeError("API error")
    result = await crm_add_note.ainvoke(
        {"entity_type": "leads", "entity_id": 1, "text": "Note"}, config=_make_config(bot_context)
    )
    assert "Ошибка" in result


async def test_crm_create_task_error(bot_context, mock_kommo):
    """crm_create_task returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_create_task

    mock_kommo.create_task.side_effect = RuntimeError("API error")
    result = await crm_create_task.ainvoke(
        {"text": "Task", "entity_id": 1, "complete_till": 9999999999},
        config=_make_config(bot_context),
    )
    assert "Ошибка" in result


async def test_crm_link_contact_to_deal_error(bot_context, mock_kommo):
    """crm_link_contact_to_deal returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_link_contact_to_deal

    mock_kommo.link_contact_to_lead.side_effect = RuntimeError("API error")
    result = await crm_link_contact_to_deal.ainvoke(
        {"lead_id": 1, "contact_id": 10}, config=_make_config(bot_context)
    )
    assert "Ошибка" in result


async def test_crm_get_contacts_error(bot_context, mock_kommo):
    """crm_get_contacts returns error string on exception."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    mock_kommo.get_contacts.side_effect = RuntimeError("API error")
    result = await crm_get_contacts.ainvoke({"query": "Ivan"}, config=_make_config(bot_context))
    assert "Ошибка" in result


# --- Task 3: Edge case tests ---


async def test_crm_tool_no_bot_context():
    """CRM tools return _CRM_UNAVAILABLE when bot_context key is missing."""
    from telegram_bot.agents.crm_tools import crm_get_deal

    result = await crm_get_deal.ainvoke({"deal_id": 1}, config={})
    assert "недоступен" in result.lower()


async def test_crm_get_contacts_truncation(bot_context, mock_kommo):
    """crm_get_contacts shows only first 10 contacts when more are returned."""
    from telegram_bot.agents.crm_tools import crm_get_contacts

    mock_kommo.get_contacts.return_value = [
        Contact(id=i, first_name=f"User{i}", last_name=f"Last{i}") for i in range(15)
    ]
    result = await crm_get_contacts.ainvoke({"query": "User"}, config=_make_config(bot_context))
    lines = [line for line in result.split("\n") if line.strip().startswith("-")]
    assert len(lines) == 10
    assert "User0" in result
    assert "User9" in result
    assert "User10" not in result


# --- Phase 2: 4 new CRM tools (#443) ---


async def test_crm_search_leads(bot_context, mock_kommo):
    """crm_search_leads returns formatted lead list."""
    from telegram_bot.agents.crm_tools import crm_search_leads

    result = await crm_search_leads.ainvoke({"query": "Alpha"}, config=_make_config(bot_context))
    assert "Alpha" in result or "20" in result
    assert "21" in result
    mock_kommo.search_leads.assert_called_once_with(query="Alpha", limit=10)


async def test_crm_search_leads_empty(bot_context, mock_kommo):
    """crm_search_leads returns not-found message when no results."""
    from telegram_bot.agents.crm_tools import crm_search_leads

    mock_kommo.search_leads.return_value = []
    result = await crm_search_leads.ainvoke({"query": "Unknown"}, config=_make_config(bot_context))
    assert "не найдены" in result.lower()


async def test_crm_search_leads_no_kommo():
    """crm_search_leads returns CRM_UNAVAILABLE when kommo_client is None."""
    from telegram_bot.agents.crm_tools import crm_search_leads

    ctx = BotContext(
        telegram_user_id=1,
        session_id="s",
        language="ru",
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
    )
    ctx.kommo_client = None
    result = await crm_search_leads.ainvoke({"query": "test"}, config=_make_config(ctx))
    assert "недоступен" in result.lower()


async def test_crm_get_my_leads(bot_context, mock_kommo):
    """crm_get_my_leads filters by manager_id."""
    from telegram_bot.agents.crm_tools import crm_get_my_leads

    result = await crm_get_my_leads.ainvoke({}, config=_make_config(bot_context))
    assert isinstance(result, str)
    mock_kommo.search_leads.assert_called_once_with(responsible_user_id=42, limit=20)


async def test_crm_get_my_leads_uses_manager_id_not_telegram_user_id(bot_context, mock_kommo):
    """Manager workflow must use ctx.manager_id for responsible_user_id filter."""
    from telegram_bot.agents.crm_tools import crm_get_my_leads

    bot_context.manager_id = 77
    mock_kommo.search_leads.return_value = [Lead(id=30, name="My Deal")]
    result = await crm_get_my_leads.ainvoke({}, config=_make_config(bot_context))
    assert isinstance(result, str)
    mock_kommo.search_leads.assert_called_once_with(responsible_user_id=77, limit=20)


async def test_crm_get_my_leads_no_manager_id(bot_context_no_manager):
    """crm_get_my_leads returns error when manager_id is None."""
    from telegram_bot.agents.crm_tools import crm_get_my_leads

    result = await crm_get_my_leads.ainvoke({}, config=_make_config(bot_context_no_manager))
    assert "manager_id" in result.lower()


async def test_crm_get_my_tasks_marks_only_incomplete_overdue(bot_context, mock_kommo):
    """Overdue marker must not be shown for completed tasks with past due date."""
    from telegram_bot.agents.crm_tools import crm_get_my_tasks

    mock_kommo.get_tasks.return_value = [
        Task(id=300, text="Overdue incomplete", complete_till=1000000000, is_completed=False),
        Task(id=301, text="Past completed", complete_till=500000000, is_completed=True),
        Task(id=302, text="Future task", complete_till=9999999999, is_completed=False),
    ]
    result = await crm_get_my_tasks.ainvoke({}, config=_make_config(bot_context))
    assert "⚠️" in result  # overdue marker for incomplete past task
    assert "Past completed" in result  # completed task still shown
    assert "- Past completed (ID: 301) ⚠️" not in result  # completed task must not be overdue
    mock_kommo.get_tasks.assert_called_once_with(responsible_user_id=42, is_completed=False)


async def test_crm_get_my_tasks_no_manager_id(bot_context_no_manager):
    """crm_get_my_tasks returns error when manager_id is None."""
    from telegram_bot.agents.crm_tools import crm_get_my_tasks

    result = await crm_get_my_tasks.ainvoke({}, config=_make_config(bot_context_no_manager))
    assert "manager_id" in result.lower()


async def test_crm_get_my_tasks_empty(bot_context, mock_kommo):
    """crm_get_my_tasks returns 'no tasks' message when list is empty."""
    from telegram_bot.agents.crm_tools import crm_get_my_tasks

    mock_kommo.get_tasks.return_value = []
    result = await crm_get_my_tasks.ainvoke({}, config=_make_config(bot_context))
    assert "нет" in result.lower()


async def test_crm_update_contact(bot_context, mock_kommo):
    """crm_update_contact calls kommo.update_contact with correct ContactUpdate."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_update_contact

    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_update_contact.ainvoke(
            {"contact_id": 50, "phone": "+111"}, config=_make_config(bot_context)
        )
    assert isinstance(result, str)
    mock_kommo.update_contact.assert_called_once()


async def test_crm_update_contact_no_kommo():
    """crm_update_contact returns CRM_UNAVAILABLE when kommo_client is None."""
    from unittest.mock import patch

    from telegram_bot.agents.crm_tools import crm_update_contact

    ctx = BotContext(
        telegram_user_id=1,
        session_id="s",
        language="ru",
        embeddings=AsyncMock(),
        sparse_embeddings=AsyncMock(),
        qdrant=AsyncMock(),
        cache=AsyncMock(),
        reranker=None,
        llm=MagicMock(),
    )
    ctx.kommo_client = None
    with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
        result = await crm_update_contact.ainvoke(
            {"contact_id": 1, "phone": "+123"}, config=_make_config(ctx)
        )
    assert "недоступен" in result.lower()


def test_get_crm_tools_count():
    """get_crm_tools returns exactly 12 tools."""
    from telegram_bot.agents.crm_tools import get_crm_tools

    tools = get_crm_tools()
    assert len(tools) == 12


@pytest.fixture
def make_config():
    def _make(ctx):
        return RunnableConfig(configurable={"bot_context": ctx})

    return _make


@pytest.fixture
def mock_state():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"service_key": "search"})
    return state


@pytest.fixture
def mock_message():
    msg = MagicMock()
    msg.text = "+380501234567"
    msg.answer = AsyncMock()
    msg.from_user = MagicMock(id=12345)
    return msg


class TestCrmCreateLeadSearchSummary:
    async def test_create_lead_adds_search_summary_note(
        self, mock_kommo, mock_state, mock_message, make_config
    ):
        """create_lead should auto-add search summary note when search_event_store is present."""
        from unittest.mock import AsyncMock, patch

        from telegram_bot.agents.crm_tools import crm_create_lead

        mock_store = AsyncMock()
        mock_store.get_user_events.return_value = [
            MagicMock(query="двушка у моря"),
            MagicMock(query="студия"),
        ]
        ctx = BotContext(
            telegram_user_id=42,
            session_id="s-1",
            language="ru",
            embeddings=AsyncMock(),
            sparse_embeddings=AsyncMock(),
            qdrant=AsyncMock(),
            cache=AsyncMock(),
            reranker=None,
            llm=MagicMock(),
            search_event_store=mock_store,
        )
        ctx.kommo_client = mock_kommo

        with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
            result = await crm_create_lead.ainvoke({"name": "Test Lead"}, config=make_config(ctx))
        assert isinstance(result, str)
        mock_kommo.add_note.assert_called_once()

    async def test_create_lead_no_store_no_note(
        self, mock_kommo, mock_state, mock_message, make_config
    ):
        """create_lead should NOT add note when search_event_store is None."""
        from unittest.mock import patch

        from telegram_bot.agents.crm_tools import crm_create_lead

        ctx = BotContext(
            telegram_user_id=42,
            session_id="s-1",
            language="ru",
            embeddings=AsyncMock(),
            sparse_embeddings=AsyncMock(),
            qdrant=AsyncMock(),
            cache=AsyncMock(),
            reranker=None,
            llm=MagicMock(),
        )
        ctx.kommo_client = mock_kommo

        with patch("telegram_bot.agents.crm_tools.hitl_guard", return_value={"action": "approve"}):
            result = await crm_create_lead.ainvoke({"name": "Test Lead"}, config=make_config(ctx))
        assert isinstance(result, str)
        mock_kommo.add_note.assert_not_called()
