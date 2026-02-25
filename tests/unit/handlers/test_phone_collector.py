# tests/unit/handlers/test_phone_collector.py
"""Tests for phone collection flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram_bot.handlers.phone_collector import (
    PhoneCollectorStates,
    _build_custom_fields,
    _build_note_text,
    build_display_name,
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


# --- build_display_name tests ---


def test_build_display_name_first_last():
    user = SimpleNamespace(first_name="Иван", last_name="Петров", username=None)
    assert build_display_name(user, "+380501234567") == "Иван П."


def test_build_display_name_first_only():
    user = SimpleNamespace(first_name="Иван", last_name=None, username=None)
    assert build_display_name(user, "+380501234567") == "Иван"


def test_build_display_name_username():
    user = SimpleNamespace(first_name=None, last_name=None, username="ivan")
    assert build_display_name(user, "+380501234567") == "@ivan"


def test_build_display_name_phone():
    assert build_display_name(None, "+380501234567") == "+380501234567"


# --- _build_custom_fields tests ---


def test_build_custom_fields_with_env_vars(monkeypatch):
    monkeypatch.setenv("KOMMO_SERVICE_FIELD_ID", "100")
    monkeypatch.setenv("KOMMO_SOURCE_FIELD_ID", "200")
    monkeypatch.setenv("KOMMO_TELEGRAM_FIELD_ID", "300")
    monkeypatch.setenv("KOMMO_TELEGRAM_USERNAME_FIELD_ID", "400")

    fields = _build_custom_fields("Осмотр объектов", 12345, "ivan")

    assert {"field_id": 100, "values": [{"value": "Осмотр объектов"}]} in fields
    assert {"field_id": 200, "values": [{"value": "Telegram-бот"}]} in fields
    assert {"field_id": 300, "values": [{"value": "12345"}]} in fields
    assert {"field_id": 400, "values": [{"value": "@ivan"}]} in fields


def test_build_custom_fields_no_env_vars(monkeypatch):
    monkeypatch.delenv("KOMMO_SERVICE_FIELD_ID", raising=False)
    monkeypatch.delenv("KOMMO_SOURCE_FIELD_ID", raising=False)
    monkeypatch.delenv("KOMMO_TELEGRAM_FIELD_ID", raising=False)
    monkeypatch.delenv("KOMMO_TELEGRAM_USERNAME_FIELD_ID", raising=False)

    fields = _build_custom_fields("Осмотр объектов", 12345, "ivan")
    assert fields == []


def test_build_custom_fields_no_username(monkeypatch):
    monkeypatch.setenv("KOMMO_SERVICE_FIELD_ID", "100")
    monkeypatch.setenv("KOMMO_TELEGRAM_USERNAME_FIELD_ID", "400")

    fields = _build_custom_fields("Осмотр объектов", 12345, None)
    field_ids = [f["field_id"] for f in fields]
    assert 100 in field_ids
    assert 400 not in field_ids


# --- _build_note_text tests ---


def test_build_note_text_basic():
    text = _build_note_text(
        crm_title="Осмотр объектов",
        phone="+380501234567",
        username="ivan",
        telegram_id=12345,
        display_name="Иван П.",
        viewing_objects=[],
    )
    assert "Осмотр объектов" in text
    assert "+380501234567" in text
    assert "@ivan" in text
    assert "Иван П." in text
    assert "Интересующие объекты" not in text


def test_build_note_text_with_viewing_objects():
    objects = [
        {
            "complex_name": "Sunny Beach",
            "property_type": "Апартамент",
            "area_m2": 45,
            "price_eur": 55000,
            "id": "apt-1",
        }
    ]
    text = _build_note_text(
        crm_title="Осмотр объектов",
        phone="+380501234567",
        username=None,
        telegram_id=12345,
        display_name="Иван",
        viewing_objects=objects,
    )
    assert "Интересующие объекты" in text
    assert "Sunny Beach" in text
    assert "55,000" in text or "55000" in text


# --- CRM integration tests ---

import telegram_bot.handlers.phone_collector as mod


async def test_on_phone_received_creates_crm_lead():
    """Valid phone with kommo_client triggers contact + lead creation in CRM."""
    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=101)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=201)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "viewing", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+359896759292"
    message.from_user = SimpleNamespace(
        id=12345, first_name="Иван", last_name="Петров", username=None
    )

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {
                "viewing": {
                    "crm_title": "Осмотр объектов",
                    "phone_success": "Спасибо! Менеджер свяжется для записи на осмотр",
                }
            }
        }
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
    message.from_user = SimpleNamespace(id=12345, first_name="Test", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {
                "viewing": {
                    "crm_title": "Осмотр объектов",
                    "phone_success": "Спасибо! Менеджер свяжется для записи на осмотр",
                }
            }
        }
        await mod.on_phone_received(message, state, kommo_client=None)

    message.answer.assert_awaited_once()
    answer_text = message.answer.call_args[0][0]
    assert "Спасибо" in answer_text


async def test_on_phone_received_uses_crm_title_in_lead_name():
    """Lead name contains crm_title from config, not raw service_key."""
    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=1)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=2)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "installment", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+380501234567"
    message.from_user = SimpleNamespace(id=99, first_name="Анна", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "services": {
                "installment": {
                    "crm_title": "Рассрочка",
                    "phone_success": "Спасибо! Менеджер свяжется с расчётом рассрочки под ваши условия",
                }
            }
        }
        await mod.on_phone_received(message, state, kommo_client=mock_kommo)

    lead_arg = mock_kommo.create_lead.call_args[0][0]
    assert "Рассрочка" in lead_arg.name
    assert "installment" not in lead_arg.name


async def test_on_phone_received_sends_personalized_success():
    """Success message comes from config phone_success, not hardcoded string."""
    state = AsyncMock()
    state.get_data.return_value = {"service_key": "infotour", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+380501234567"
    message.from_user = SimpleNamespace(id=1, first_name="X", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "services": {
                "infotour": {
                    "crm_title": "Инфотур",
                    "phone_success": "Спасибо! Менеджер свяжется для бронирования инфотура",
                }
            }
        }
        await mod.on_phone_received(message, state, kommo_client=None)

    answer_text = message.answer.call_args[0][0]
    assert "бронирования инфотура" in answer_text
