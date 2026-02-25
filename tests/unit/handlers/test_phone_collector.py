# tests/unit/handlers/test_phone_collector.py
"""Tests for phone collection flow."""

from telegram_bot.handlers.phone_collector import (
    PhoneCollectorStates,
    create_phone_router,
    validate_phone,
)


def test_validate_phone_valid():
    assert validate_phone("+380501234567") is True
    assert validate_phone("+359896759292") is True
    assert validate_phone("0501234567") is True


def test_validate_phone_invalid():
    assert validate_phone("hello") is False
    assert validate_phone("") is False
    assert validate_phone("123") is False


def test_states_defined():
    assert hasattr(PhoneCollectorStates, "waiting_phone")


def test_create_phone_router_returns_fresh_instance():
    """Router factory must return a new instance for each bot/dispatcher."""
    router_a = create_phone_router()
    router_b = create_phone_router()

    assert router_a is not router_b
    assert router_a.name == "phone_collector"
    assert router_b.name == "phone_collector"


# --- CRM integration tests ---

from types import SimpleNamespace
from unittest.mock import AsyncMock

import telegram_bot.handlers.phone_collector as mod


async def test_on_phone_received_creates_crm_lead():
    """Valid phone with kommo_client triggers contact + lead creation in CRM."""
    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=101)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=201)

    state = AsyncMock()
    state.get_data.return_value = {
        "service_key": "viewing",
        "viewing_objects": [{"id": "prop-42", "complex_name": "Test"}],
    }

    message = AsyncMock()
    message.text = "+359896759292"
    message.from_user = SimpleNamespace(id=12345, first_name="Иван", last_name="Петров")

    await mod.on_phone_received(message, state, kommo_client=mock_kommo)

    mock_kommo.upsert_contact.assert_awaited_once()
    mock_kommo.create_lead.assert_awaited_once()
    mock_kommo.link_contact_to_lead.assert_awaited_once_with(201, 101)
    answer_text = message.answer.call_args[0][0]
    assert "Спасибо" in answer_text


async def test_on_phone_received_works_without_kommo():
    """Valid phone without kommo_client still replies to user and does not raise."""
    state = AsyncMock()
    state.get_data.return_value = {"service_key": "viewing", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+359896759292"
    message.from_user = SimpleNamespace(id=12345, first_name="Test", last_name=None)

    await mod.on_phone_received(message, state, kommo_client=None)

    message.answer.assert_awaited_once()
    answer_text = message.answer.call_args[0][0]
    assert "Спасибо" in answer_text
