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
    normalize_phone,
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


# --- normalize_phone tests (Task 3: phonenumbers validation) ---


def test_normalize_phone_returns_e164_for_valid_international():
    assert normalize_phone("+380501234567") == "+380501234567"
    assert normalize_phone("+359896759292") == "+359896759292"


def test_normalize_phone_returns_none_for_all_same_digits():
    """Fake numbers like 0000000000 or 1111111 must be rejected."""
    assert normalize_phone("+00000000000") is None
    assert normalize_phone("+11111111111") is None


def test_normalize_phone_returns_none_for_non_numeric():
    assert normalize_phone("hello") is None
    assert normalize_phone("") is None


def test_normalize_phone_returns_none_for_too_short():
    assert normalize_phone("+123") is None


def test_normalize_phone_normalizes_formatting():
    """Spaces and dashes are cleaned before parsing."""
    assert normalize_phone("+38 050 123-45-67") == "+380501234567"


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


def test_build_custom_fields_with_explicit_field_ids():
    fields = _build_custom_fields(
        "Осмотр объектов",
        12345,
        "ivan",
        service_field_id=100,
        source_field_id=200,
        telegram_field_id=300,
        telegram_username_field_id=400,
    )

    assert {"field_id": 100, "values": [{"value": "Осмотр объектов"}]} in fields
    assert {"field_id": 200, "values": [{"value": "Telegram-бот"}]} in fields
    assert {"field_id": 300, "values": [{"value": "12345"}]} in fields
    assert {"field_id": 400, "values": [{"value": "@ivan"}]} in fields


def test_build_custom_fields_no_field_ids_returns_empty():
    fields = _build_custom_fields("Осмотр объектов", 12345, "ivan")
    assert fields == []


def test_build_custom_fields_no_username():
    fields = _build_custom_fields(
        "Осмотр объектов",
        12345,
        None,
        service_field_id=100,
        telegram_username_field_id=400,
    )
    field_ids = [f["field_id"] for f in fields]
    assert 100 in field_ids
    assert 400 not in field_ids


def test_build_custom_fields_zero_field_ids_returns_empty():
    fields = _build_custom_fields(
        "Осмотр объектов",
        12345,
        "ivan",
        service_field_id=0,
        source_field_id=0,
        telegram_field_id=0,
        telegram_username_field_id=0,
    )
    assert fields == []


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


async def test_on_phone_received_none_responsible_id_does_not_break_crm():
    """bot_config.kommo_responsible_user_id=None should not abort lead creation."""
    bot_config = SimpleNamespace(
        kommo_default_pipeline_id=0,
        kommo_new_status_id=0,
        kommo_responsible_user_id=None,
        kommo_service_field_id=0,
        kommo_source_field_id=0,
        kommo_telegram_field_id=0,
        kommo_telegram_username_field_id=0,
    )

    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=7)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=8)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "manager", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+380501234567"
    message.from_user = SimpleNamespace(id=321, first_name="Иван", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {
                "manager": {
                    "crm_title": "Консультация",
                    "phone_success": "Спасибо! Менеджер свяжется с вами в ближайшее время",
                }
            }
        }
        await mod.on_phone_received(message, state, kommo_client=mock_kommo, bot_config=bot_config)

    mock_kommo.create_lead.assert_awaited_once()


async def test_on_phone_received_zero_responsible_id_normalized_to_none():
    """bot_config.kommo_responsible_user_id=0 should be normalized to None."""
    bot_config = SimpleNamespace(
        kommo_default_pipeline_id=0,
        kommo_new_status_id=0,
        kommo_responsible_user_id=0,
        kommo_service_field_id=0,
        kommo_source_field_id=0,
        kommo_telegram_field_id=0,
        kommo_telegram_username_field_id=0,
    )

    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=17)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=18)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "manager", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+380501234567"
    message.from_user = SimpleNamespace(id=654, first_name="Иван", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {
                "manager": {
                    "crm_title": "Консультация",
                    "phone_success": "Спасибо! Менеджер свяжется с вами в ближайшее время",
                }
            }
        }
        await mod.on_phone_received(message, state, kommo_client=mock_kommo, bot_config=bot_config)

    mock_kommo.create_lead.assert_awaited_once()
    lead_arg = mock_kommo.create_lead.call_args[0][0]
    assert lead_arg.responsible_user_id is None


# --- BotConfig injection tests (new API, RED first) ---


def test_build_custom_fields_with_explicit_ids():
    """_build_custom_fields must accept explicit field IDs without reading env vars."""
    fields = _build_custom_fields(
        "Осмотр",
        12345,
        "ivan",
        service_field_id=100,
        source_field_id=200,
        telegram_field_id=300,
        telegram_username_field_id=400,
    )
    assert len(fields) == 4
    assert {"field_id": 100, "values": [{"value": "Осмотр"}]} in fields
    assert {"field_id": 200, "values": [{"value": "Telegram-бот"}]} in fields
    assert {"field_id": 300, "values": [{"value": "12345"}]} in fields
    assert {"field_id": 400, "values": [{"value": "@ivan"}]} in fields


def test_build_custom_fields_explicit_zero_ids_returns_empty():
    """When all explicit field IDs are 0 (default), no fields are added."""
    fields = _build_custom_fields("Осмотр", 12345, "ivan")
    assert fields == []


async def test_on_phone_received_uses_bot_config_for_pipeline_ids():
    """on_phone_received must read pipeline/status/responsible IDs from bot_config, not env vars."""
    bot_config = SimpleNamespace(
        kommo_default_pipeline_id=55,
        kommo_new_status_id=77,
        kommo_responsible_user_id=88,
        kommo_service_field_id=100,
        kommo_source_field_id=200,
        kommo_telegram_field_id=300,
        kommo_telegram_username_field_id=400,
    )

    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=10)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=20)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "viewing", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+380501234567"
    message.from_user = SimpleNamespace(id=99, first_name="Анна", last_name=None, username="anna")

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {
                "viewing": {
                    "crm_title": "Осмотр объектов",
                    "phone_success": "Спасибо!",
                }
            }
        }
        await mod.on_phone_received(message, state, kommo_client=mock_kommo, bot_config=bot_config)

    mock_kommo.create_lead.assert_awaited_once()
    lead_arg = mock_kommo.create_lead.call_args[0][0]
    assert lead_arg.pipeline_id == 55
    assert lead_arg.status_id == 77
    assert lead_arg.responsible_user_id == 88


# --- Task 4: normalize_phone in on_phone_received ---


async def test_on_phone_received_passes_phone_to_contact_create():
    """on_phone_received must pass phone to ContactCreate so it reaches Kommo."""
    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=5)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=6)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "viewing", "viewing_objects": []}

    message = AsyncMock()
    message.text = "+380501234567"
    message.from_user = SimpleNamespace(id=1, first_name="Иван", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {"viewing": {"crm_title": "X", "phone_success": "OK"}}
        }
        await mod.on_phone_received(message, state, kommo_client=mock_kommo)

    upsert_call = mock_kommo.upsert_contact.call_args
    contact_create_arg = upsert_call[0][1]  # second positional arg is ContactCreate
    # phone must be passed so upsert_contact can put it in custom_fields_values
    assert contact_create_arg.phone == "+380501234567"


async def test_on_phone_received_normalizes_phone_to_e164():
    """Phone is normalized to E164 before storing in CRM."""
    mock_kommo = AsyncMock()
    mock_kommo.upsert_contact.return_value = SimpleNamespace(id=5)
    mock_kommo.create_lead.return_value = SimpleNamespace(id=6)

    state = AsyncMock()
    state.get_data.return_value = {"service_key": "viewing", "viewing_objects": []}

    message = AsyncMock()
    # Phone with spaces/dashes — normalize_phone should clean it to E164
    message.text = "+38 050 123-45-67"
    message.from_user = SimpleNamespace(id=1, first_name="Иван", last_name=None, username=None)

    with patch("telegram_bot.services.content_loader.load_services_config") as mock_cfg:
        mock_cfg.return_value = {
            "entry_points": {"viewing": {"crm_title": "X", "phone_success": "OK"}}
        }
        await mod.on_phone_received(message, state, kommo_client=mock_kommo)

    upsert_call = mock_kommo.upsert_contact.call_args
    phone_arg = upsert_call[0][0]  # first positional arg is phone string
    assert phone_arg == "+380501234567"  # E164 normalized


async def test_on_phone_received_rejects_fake_phone_even_if_regex_matches():
    """Numbers rejected by phonenumbers must not pass through raw fallback."""
    mock_kommo = AsyncMock()
    state = AsyncMock()
    message = AsyncMock()
    message.text = "+11111111111"
    message.from_user = SimpleNamespace(id=1, first_name="Иван", last_name=None, username=None)

    await mod.on_phone_received(message, state, kommo_client=mock_kommo)

    mock_kommo.upsert_contact.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert "корректный номер телефона" in message.answer.call_args[0][0]


async def test_phone_error_message_shows_format_mask():
    """Fallback error message should show +380 XX XXX XXXX, not +380501234567."""
    state = AsyncMock()
    message = AsyncMock()
    message.text = "invalid"
    message.from_user = SimpleNamespace(id=1, first_name="Test", last_name=None, username=None)

    await mod.on_phone_received(message, state)

    call_text = message.answer.call_args[0][0]
    assert "+380 XX XXX XXXX" in call_text
    assert "+380501234567" not in call_text
