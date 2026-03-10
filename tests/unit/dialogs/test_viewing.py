"""Tests for viewing appointment wizard dialog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.states import ViewingSG


def test_viewing_sg_has_all_states():
    assert hasattr(ViewingSG, "date")
    assert hasattr(ViewingSG, "phone")
    assert hasattr(ViewingSG, "summary")
    # objects states removed
    assert not hasattr(ViewingSG, "objects")
    assert not hasattr(ViewingSG, "objects_text")


# --- Date options ---


@pytest.mark.asyncio
async def test_get_date_options_returns_5_items():
    from telegram_bot.dialogs.viewing import get_date_options

    result = await get_date_options()
    items = result["items"]
    assert len(items) == 5
    keys = [key for _, key in items]
    assert "nearest" in keys
    assert "next_week" in keys
    assert "next_month" in keys
    assert "unknown" in keys
    assert "phone" in keys


# --- Date handler ---


@pytest.mark.asyncio
async def test_on_date_selected_saves_and_switches_to_phone():
    from telegram_bot.dialogs.viewing import on_date_selected

    callback = MagicMock()
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.from_user = SimpleNamespace(id=123)
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_date_selected(callback, SimpleNamespace(), manager, "next_week")
    assert manager.dialog_data["date_range"] == "next_week"
    manager.switch_to.assert_awaited_once_with(ViewingSG.phone)
    # Should send ReplyKeyboard with request_contact
    callback.bot.send_message.assert_awaited_once()


# --- Summary getter ---


@pytest.mark.asyncio
async def test_get_summary_data_formats_all_fields():
    from telegram_bot.dialogs.viewing import get_summary_data

    manager = SimpleNamespace(
        dialog_data={
            "date_range": "nearest",
            "phone": "+380990091392",
        }
    )
    result = await get_summary_data(dialog_manager=manager)
    assert "+380990091392" in result["summary_text"]
    assert "Ближайшие дни" in result["summary_text"]
    # Objects section removed from summary
    assert "Объекты" not in result["summary_text"]


# --- Due date calculation ---


def test_compute_due_date_nearest():
    import time

    from telegram_bot.dialogs.viewing import compute_due_date

    now = int(time.time())
    due = compute_due_date("nearest")
    # nearest = +3 days
    assert abs(due - now - 3 * 86400) < 5


def test_compute_due_date_unknown_defaults_7_days():
    import time

    from telegram_bot.dialogs.viewing import compute_due_date

    now = int(time.time())
    due = compute_due_date("unknown")
    assert abs(due - now - 7 * 86400) < 5


# --- Dialog structure ---


def test_viewing_dialog_exists():
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.viewing import viewing_dialog

    assert isinstance(viewing_dialog, Dialog)


def test_viewing_dialog_has_all_windows():
    from telegram_bot.dialogs.viewing import viewing_dialog

    windows = viewing_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ViewingSG.date in states
    assert ViewingSG.phone in states
    assert ViewingSG.summary in states


def test_viewing_dialog_importable_from_module():
    """Verify viewing_dialog can be imported (registration sanity check)."""
    from telegram_bot.dialogs.viewing import viewing_dialog

    assert viewing_dialog is not None
    assert len(viewing_dialog.windows) == 3


@pytest.mark.asyncio
async def test_phone_prompt_contains_format_mask():
    """Phone prompt should show format examples (BG + UA)."""
    from telegram_bot.dialogs.viewing import get_phone_prompt

    result = await get_phone_prompt()
    assert "+359" in result["title"]


@pytest.mark.asyncio
async def test_on_date_selected_sends_reply_keyboard():
    """on_date_selected should send ReplyKeyboard with request_contact."""
    from telegram_bot.dialogs.viewing import on_date_selected

    callback = MagicMock()
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.from_user = SimpleNamespace(id=456)
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_date_selected(callback, SimpleNamespace(), manager, "nearest")
    # Should send ReplyKeyboard via bot.send_message
    callback.bot.send_message.assert_awaited_once()
    call_kwargs = callback.bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 456
    assert call_kwargs["reply_markup"] is not None


# --- CRM integration ---


@pytest.mark.asyncio
async def test_phone_text_handler_sets_delete_and_send_mode():
    """After phone input, dialog should DELETE_AND_SEND to avoid stale messages."""
    from aiogram_dialog import ShowMode

    from telegram_bot.dialogs.viewing import on_phone_text_received

    manager = AsyncMock()
    manager.dialog_data = {}
    message = AsyncMock()
    message.text = "+380501234567"

    await on_phone_text_received(message, None, manager)

    assert manager.show_mode == ShowMode.DELETE_AND_SEND
    assert manager.dialog_data["phone"] == "+380501234567"
    manager.switch_to.assert_awaited_once_with(ViewingSG.summary)


@pytest.mark.asyncio
async def test_phone_contact_auto_confirm():
    """Contact share should auto-confirm: submit CRM and call manager.done()."""
    from aiogram_dialog import ShowMode

    from telegram_bot.dialogs.viewing import on_phone_contact_received

    manager = AsyncMock()
    manager.dialog_data = {"date_range": "nearest"}
    manager.middleware_data = {"kommo_client": None, "bot_config": None}
    message = AsyncMock()
    message.contact = MagicMock()
    message.contact.phone_number = "+380501234567"
    message.from_user = SimpleNamespace(
        id=12345, first_name="Test", last_name=None, username="testuser"
    )
    message.bot = AsyncMock()

    await on_phone_contact_received(message, None, manager)

    assert manager.show_mode == ShowMode.EDIT
    assert manager.dialog_data["phone"] == "+380501234567"
    # Should call done() directly (no switch to summary)
    manager.done.assert_awaited_once()
    # Should NOT switch to summary
    manager.switch_to.assert_not_awaited()
    # Should send confirmation message
    message.bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_confirm_creates_crm_entities():
    from telegram_bot.dialogs.viewing import on_confirm

    kommo = AsyncMock()
    kommo.upsert_contact.return_value = SimpleNamespace(id=100)
    kommo.create_lead.return_value = SimpleNamespace(id=200)

    bot_config = SimpleNamespace(
        kommo_default_pipeline_id=0,
        kommo_new_status_id=0,
        kommo_responsible_user_id=None,
        kommo_service_field_id=0,
        kommo_source_field_id=0,
        kommo_telegram_field_id=0,
        kommo_telegram_username_field_id=0,
    )

    callback = MagicMock()
    callback.from_user = SimpleNamespace(
        id=12345, first_name="Test", last_name=None, username="testuser"
    )
    callback.bot = AsyncMock()
    callback.answer = AsyncMock()

    manager = MagicMock()
    manager.dialog_data = {
        "date_range": "nearest",
        "phone": "+380990091392",
    }
    manager.middleware_data = {
        "kommo_client": kommo,
        "bot_config": bot_config,
    }
    manager.done = AsyncMock()

    await on_confirm(callback, MagicMock(), manager)

    kommo.upsert_contact.assert_awaited_once()
    kommo.create_lead.assert_awaited_once()
    # Lead name should NOT contain objects (simplified)
    lead_arg = kommo.create_lead.await_args.args[0]
    assert "Осмотр —" in lead_arg.name
    kommo.link_contact_to_lead.assert_awaited_once_with(200, 100)
    kommo.add_note.assert_awaited_once()
    note_text = kommo.add_note.await_args.args[2]
    assert "Запись на осмотр" in note_text
    assert "+380990091392" in note_text
    kommo.create_task.assert_awaited_once()
    callback.bot.send_message.assert_awaited_once()
    manager.done.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_confirm_graceful_when_no_kommo():
    from telegram_bot.dialogs.viewing import on_confirm

    callback = MagicMock()
    callback.from_user = SimpleNamespace(id=12345, first_name="Test", last_name=None, username=None)
    callback.bot = AsyncMock()
    callback.answer = AsyncMock()

    manager = MagicMock()
    manager.dialog_data = {
        "date_range": "unknown",
        "phone": "+380990091392",
    }
    manager.middleware_data = {"kommo_client": None, "bot_config": None}
    manager.done = AsyncMock()

    # Should not raise
    await on_confirm(callback, MagicMock(), manager)
    callback.bot.send_message.assert_awaited_once()
    # Verify confirmation goes to correct chat with expected text
    send_kwargs = callback.bot.send_message.await_args
    assert send_kwargs.kwargs["chat_id"] == 12345
    assert "заявка на осмотр получена" in send_kwargs.kwargs["text"].lower()
    manager.done.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_confirm_sends_confirmation_with_correct_text():
    """Confirmation message MUST be sent to user's chat after form submission."""
    from telegram_bot.dialogs.viewing import on_confirm

    kommo = AsyncMock()
    kommo.upsert_contact.return_value = SimpleNamespace(id=100)
    kommo.create_lead.return_value = SimpleNamespace(id=200)

    bot_config = SimpleNamespace(
        kommo_default_pipeline_id=0,
        kommo_new_status_id=0,
        kommo_responsible_user_id=None,
        kommo_service_field_id=0,
        kommo_source_field_id=0,
        kommo_telegram_field_id=0,
        kommo_telegram_username_field_id=0,
    )

    callback = MagicMock()
    callback.from_user = SimpleNamespace(
        id=99999, first_name="Maria", last_name=None, username="maria_bg"
    )
    callback.bot = AsyncMock()

    manager = MagicMock()
    manager.dialog_data = {
        "date_range": "next_week",
        "phone": "+359881234567",
    }
    manager.middleware_data = {"kommo_client": kommo, "bot_config": bot_config}
    manager.done = AsyncMock()

    await on_confirm(callback, MagicMock(), manager)

    # 1. Confirmation message sent to the user
    callback.bot.send_message.assert_awaited_once()
    call_kwargs = callback.bot.send_message.await_args.kwargs
    assert call_kwargs["chat_id"] == 99999
    assert "заявка на осмотр получена" in call_kwargs["text"].lower()
    assert "менеджер свяжется" in call_kwargs["text"].lower()

    # 2. Lead title simplified (no objects)
    lead_arg = kommo.create_lead.await_args.args[0]
    assert "Осмотр —" in lead_arg.name

    # 3. Dialog closed
    manager.done.assert_awaited_once()


# --- Cancel → HandoffSG ---


@pytest.mark.asyncio
async def test_cancel_starts_handoff_dialog():
    """Cancel button should start HandoffSG.goal dialog."""
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.states import HandoffSG
    from telegram_bot.dialogs.viewing import on_cancel_to_manager

    manager = AsyncMock()
    callback = MagicMock()

    await on_cancel_to_manager(callback, MagicMock(), manager)

    manager.start.assert_awaited_once_with(HandoffSG.goal, mode=StartMode.RESET_STACK)
