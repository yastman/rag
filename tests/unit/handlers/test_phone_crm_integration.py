# tests/unit/handlers/test_phone_crm_integration.py
"""TDD tests for phone collector -> Kommo CRM integration (#660)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.kommo_models import Contact, Lead, Note, Task


@pytest.fixture
def mock_kommo():
    """AsyncMock Kommo client with all required methods."""
    kommo = AsyncMock()
    kommo.upsert_contact = AsyncMock(return_value=Contact(id=1, first_name="Iван"))
    kommo.create_lead = AsyncMock(return_value=Lead(id=101, name="Консультация — Iван"))
    kommo.link_contact_to_lead = AsyncMock(return_value=None)
    kommo.create_task = AsyncMock(return_value=Task(id=201, entity_id=101))
    kommo.add_note = AsyncMock(return_value=Note(id=301))
    return kommo


@pytest.fixture
def mock_message():
    """AsyncMock aiogram Message with phone text."""
    from types import SimpleNamespace

    msg = AsyncMock()
    msg.text = "+380501234567"
    msg.from_user = SimpleNamespace(id=12345, first_name="Iван", last_name=None, username=None)
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_state():
    """AsyncMock FSMContext returning service_key."""
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"service_key": "manager", "viewing_objects": []})
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_config():
    """Patch load_services_config with test data."""
    return {
        "entry_points": {
            "manager": {
                "crm_title": "Консультация",
                "phone_success": "Спасибо! Менеджер свяжется с вами в ближайшее время",
            }
        }
    }


async def test_creates_contact_and_lead(mock_kommo, mock_message, mock_state, mock_config):
    """on_phone_received creates CRM contact and lead when kommo_client provided."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    with patch(
        "telegram_bot.services.content_loader.load_services_config", return_value=mock_config
    ):
        await on_phone_received(mock_message, mock_state, kommo_client=mock_kommo)

    mock_kommo.upsert_contact.assert_awaited_once()
    call_phone = mock_kommo.upsert_contact.call_args[0][0]
    assert call_phone == "+380501234567"

    mock_kommo.create_lead.assert_awaited_once()
    mock_kommo.link_contact_to_lead.assert_awaited_once_with(101, 1)


async def test_creates_manager_task(mock_kommo, mock_message, mock_state, mock_config):
    """on_phone_received creates a manager callback task with phone in text and correct entity_id."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    with patch(
        "telegram_bot.services.content_loader.load_services_config", return_value=mock_config
    ):
        await on_phone_received(mock_message, mock_state, kommo_client=mock_kommo)

    mock_kommo.create_task.assert_awaited_once()
    task_arg = mock_kommo.create_task.call_args[0][0]
    assert "+380501234567" in task_arg.text
    assert task_arg.entity_id == 101  # lead.id


async def test_graceful_when_kommo_disabled(mock_message, mock_state, mock_config):
    """on_phone_received still sends thank-you message when kommo_client=None."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    with patch(
        "telegram_bot.services.content_loader.load_services_config", return_value=mock_config
    ):
        await on_phone_received(mock_message, mock_state, kommo_client=None)

    mock_message.answer.assert_awaited_once()
    text = mock_message.answer.call_args[0][0]
    assert "Спасибо" in text


async def test_graceful_on_kommo_error(mock_kommo, mock_message, mock_state, mock_config):
    """on_phone_received still sends thank-you message when Kommo raises an exception."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    mock_kommo.upsert_contact.side_effect = Exception("Kommo API down")

    with patch(
        "telegram_bot.services.content_loader.load_services_config", return_value=mock_config
    ):
        await on_phone_received(mock_message, mock_state, kommo_client=mock_kommo)

    mock_message.answer.assert_awaited_once()
    text = mock_message.answer.call_args[0][0]
    assert "Спасибо" in text


async def test_source_tracking_in_lead_name(mock_kommo, mock_message, mock_state, mock_config):
    """Lead name includes crm_title (not raw service_key) from FSM state data."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    with patch(
        "telegram_bot.services.content_loader.load_services_config", return_value=mock_config
    ):
        await on_phone_received(mock_message, mock_state, kommo_client=mock_kommo)

    mock_kommo.create_lead.assert_awaited_once()
    lead_arg = mock_kommo.create_lead.call_args[0][0]
    # crm_title "Консультация" should be in the lead name
    assert "Консультация" in lead_arg.name
