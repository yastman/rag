"""Tests for Kommo CRM supervisor tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.kommo_models import (
    ContactResponse,
    DealDraft,
    LeadResponse,
    NoteResponse,
    TaskResponse,
)


@pytest.fixture
def mock_kommo():
    client = AsyncMock()
    client.create_lead = AsyncMock(return_value=LeadResponse(id=100, name="Test", price=50000))
    client.upsert_contact = AsyncMock(return_value=ContactResponse(id=200, name="Иван"))
    client.link_contact_to_lead = AsyncMock()
    client.add_note = AsyncMock(return_value=NoteResponse(id=300))
    client.create_task = AsyncMock(return_value=TaskResponse(id=400, text="Follow up"))
    return client


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_history():
    svc = AsyncMock()
    svc.get_session_turns = AsyncMock(
        return_value=[
            {"role": "user", "content": "Ищу квартиру в Несебре, бюджет 50000"},
            {"role": "assistant", "content": "Могу предложить 2-комнатную..."},
            {"role": "user", "content": "Отлично! Меня зовут Иван, телефон +380501234567"},
        ]
    )
    return svc


@pytest.fixture
def runnable_config():
    return {"configurable": {"user_id": 12345, "session_id": "chat_789"}}


class TestCreateCrmTools:
    def test_returns_list_of_tools(self, mock_kommo, mock_llm, mock_history):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
        )
        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "crm_generate_deal_draft" in tool_names
        assert "crm_upsert_contact" in tool_names
        assert "crm_create_deal" in tool_names
        assert "crm_link_contact_to_deal" in tool_names
        assert "crm_add_note" in tool_names
        assert "crm_create_followup_task" in tool_names
        assert "crm_finalize_deal" in tool_names


class TestCrmUpsertContact:
    async def test_upsert_contact_tool(self, mock_kommo, mock_llm, mock_history, runnable_config):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
        )
        upsert_tool = next(t for t in tools if t.name == "crm_upsert_contact")
        result = await upsert_tool.ainvoke(
            {"phone": "+380501234567", "first_name": "Иван"},
            config=runnable_config,
        )
        assert "200" in result or "Иван" in result
        mock_kommo.upsert_contact.assert_called_once()


class TestCrmCreateDeal:
    async def test_create_deal_tool(self, mock_kommo, mock_llm, mock_history, runnable_config):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
        )
        deal_tool = next(t for t in tools if t.name == "crm_create_deal")
        result = await deal_tool.ainvoke(
            {"name": "Квартира в Несебре", "price": 50000},
            config=runnable_config,
        )
        assert "100" in result  # lead ID in response
        mock_kommo.create_lead.assert_called_once()


class TestCrmAddNote:
    async def test_add_note_tool(self, mock_kommo, mock_llm, mock_history, runnable_config):
        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
        )
        note_tool = next(t for t in tools if t.name == "crm_add_note")
        result = await note_tool.ainvoke(
            {"deal_id": 100, "text": "Клиент заинтересован"},
            config=runnable_config,
        )
        assert "300" in result  # note ID
        mock_kommo.add_note.assert_called_once()


class TestCrmFinalizeDeal:
    async def test_finalize_deal_orchestrates_all_steps(
        self, mock_kommo, mock_llm, mock_history, runnable_config
    ):
        # Mock LLM to return structured DealDraft
        draft = DealDraft(
            client_name="Иван Петров",
            phone="+380501234567",
            budget=50000,
            property_type="квартира",
            location="Несебр",
            notes="2-комнатная у моря",
        )
        mock_llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content=draft.model_dump_json()))]
            )
        )

        from telegram_bot.agents.crm_tools import create_crm_tools

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
        )
        finalize_tool = next(t for t in tools if t.name == "crm_finalize_deal")
        result = await finalize_tool.ainvoke(
            {"query": "создай сделку"},
            config=runnable_config,
        )

        # All steps should be called
        mock_kommo.upsert_contact.assert_called_once()
        mock_kommo.create_lead.assert_called_once()
        mock_kommo.link_contact_to_lead.assert_called_once_with(lead_id=100, contact_id=200)
        mock_kommo.add_note.assert_called_once()
        mock_kommo.create_task.assert_called_once()
        assert "100" in result  # lead ID in response

    async def test_finalize_deal_idempotent_skip(
        self, mock_kommo, mock_llm, mock_history, runnable_config
    ):
        from telegram_bot.agents.crm_tools import create_crm_tools

        # redis-like idempotency store: first call sets key, second sees duplicate
        idem_store = AsyncMock()
        idem_store.set = AsyncMock(side_effect=[True, False])

        draft = DealDraft(
            client_name="Иван",
            phone="+380501234567",
            budget=50000,
        )
        mock_llm.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content=draft.model_dump_json()))]
            )
        )

        tools = create_crm_tools(
            kommo=mock_kommo,
            llm=mock_llm,
            history_service=mock_history,
            default_pipeline_id=1,
            responsible_user_id=None,
            session_field_id=123,
            idempotency_store=idem_store,
        )
        finalize_tool = next(t for t in tools if t.name == "crm_finalize_deal")
        await finalize_tool.ainvoke({"query": "создай сделку"}, config=runnable_config)
        second = await finalize_tool.ainvoke({"query": "создай сделку"}, config=runnable_config)

        assert "idempotent" in second.lower() or "already" in second.lower()
