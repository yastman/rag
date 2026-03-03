"""Tests for viewing appointment wizard dialog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.states import ViewingSG


def test_viewing_sg_has_all_states():
    assert hasattr(ViewingSG, "objects")
    assert hasattr(ViewingSG, "objects_text")
    assert hasattr(ViewingSG, "date")
    assert hasattr(ViewingSG, "phone")
    assert hasattr(ViewingSG, "summary")


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
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_date_selected(callback, SimpleNamespace(), manager, "next_week")
    assert manager.dialog_data["date_range"] == "next_week"
    manager.switch_to.assert_awaited_once_with(ViewingSG.phone)


# --- Objects getter (empty favorites) ---


@pytest.mark.asyncio
async def test_get_objects_options_empty_favorites():
    from telegram_bot.dialogs.viewing import get_objects_options

    result = await get_objects_options(
        event_from_user=SimpleNamespace(id=12345),
        favorites_service=None,
    )
    items = result["items"]
    assert len(items) == 0
    assert result["has_favorites"] is False


@pytest.mark.asyncio
async def test_get_objects_options_reads_favorites_from_middleware_data():
    from telegram_bot.dialogs.viewing import get_objects_options

    favorites_service = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                SimpleNamespace(
                    property_id="prop-1",
                    property_data={
                        "complex_name": "Sunset",
                        "property_type": "1+1",
                        "area_m2": 61,
                        "price_eur": 95000,
                    },
                )
            ]
        )
    )
    manager = SimpleNamespace(dialog_data={})

    result = await get_objects_options(
        event_from_user=SimpleNamespace(id=12345),
        middleware_data={"favorites_service": favorites_service},
        dialog_manager=manager,
    )

    assert result["has_favorites"] is True
    assert len(result["items"]) == 1
    assert result["items"][0][1] == "prop-1"
    assert "Sunset" in result["items"][0][0]
    assert manager.dialog_data["favorites_by_id"]["prop-1"]["complex_name"] == "Sunset"


# --- Objects skip handler ---


@pytest.mark.asyncio
async def test_on_objects_skip_switches_to_date():
    from telegram_bot.dialogs.viewing import on_objects_skip

    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_objects_skip(MagicMock(), MagicMock(), manager)
    manager.switch_to.assert_awaited_once_with(ViewingSG.date)


@pytest.mark.asyncio
async def test_on_object_selected_keeps_object_metadata_for_summary_and_crm():
    from telegram_bot.dialogs.viewing import on_object_selected

    manager = SimpleNamespace(
        dialog_data={
            "favorites_by_id": {
                "prop-1": {
                    "id": "prop-1",
                    "complex_name": "Sunset",
                    "property_type": "1+1",
                    "area_m2": 61,
                    "price_eur": 95000,
                }
            }
        }
    )

    await on_object_selected(MagicMock(), MagicMock(), manager, "prop-1")

    selected = manager.dialog_data["selected_objects"]
    assert len(selected) == 1
    assert selected[0]["id"] == "prop-1"
    assert selected[0]["complex_name"] == "Sunset"
    assert selected[0]["price_eur"] == 95000


# --- Summary getter ---


@pytest.mark.asyncio
async def test_get_summary_data_formats_all_fields():
    from telegram_bot.dialogs.viewing import get_summary_data

    manager = SimpleNamespace(
        dialog_data={
            "selected_objects": [{"complex_name": "Sunset", "property_type": "1+1"}],
            "date_range": "nearest",
            "phone": "+380990091392",
        }
    )
    result = await get_summary_data(dialog_manager=manager)
    assert "+380990091392" in result["summary_text"]
    assert "Sunset" in result["summary_text"]
    assert "Ближайшие дни" in result["summary_text"]


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
    assert ViewingSG.objects in states
    assert ViewingSG.objects_text in states
    assert ViewingSG.date in states
    assert ViewingSG.phone in states
    assert ViewingSG.summary in states


def test_viewing_dialog_importable_from_module():
    """Verify viewing_dialog can be imported (registration sanity check)."""
    from telegram_bot.dialogs.viewing import viewing_dialog

    assert viewing_dialog is not None
    assert len(viewing_dialog.windows) == 5


@pytest.mark.asyncio
async def test_phone_prompt_contains_format_mask():
    """Phone prompt should show format examples (BG + UA)."""
    from telegram_bot.dialogs.viewing import get_phone_prompt

    result = await get_phone_prompt()
    assert "+359" in result["title"]


@pytest.mark.asyncio
async def test_on_date_selected_no_extra_message():
    """on_date_selected should NOT send extra reply keyboard message."""
    from telegram_bot.dialogs.viewing import on_date_selected

    callback = MagicMock()
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_date_selected(callback, SimpleNamespace(), manager, "nearest")
    # No extra message should be sent
    callback.message.answer.assert_not_called()


# --- CRM integration ---


@pytest.mark.asyncio
async def test_phone_text_handler_sets_edit_mode():
    """After phone input, dialog should EDIT existing message, not SEND new."""
    from aiogram_dialog import ShowMode

    from telegram_bot.dialogs.viewing import on_phone_text_received

    manager = AsyncMock()
    manager.dialog_data = {}
    message = AsyncMock()
    message.text = "+380501234567"

    await on_phone_text_received(message, None, manager)

    assert manager.show_mode == ShowMode.EDIT


@pytest.mark.asyncio
async def test_phone_contact_handler_sets_edit_mode():
    """After contact share, dialog should EDIT existing message, not SEND new."""
    from aiogram_dialog import ShowMode

    from telegram_bot.dialogs.viewing import on_phone_contact_received

    manager = AsyncMock()
    manager.dialog_data = {}
    message = AsyncMock()
    message.contact = MagicMock()
    message.contact.phone_number = "+380501234567"

    await on_phone_contact_received(message, None, manager)

    assert manager.show_mode == ShowMode.EDIT


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
        "selected_objects": [
            {
                "id": "prop-1",
                "complex_name": "Sunset",
                "property_type": "1+1",
                "area_m2": 61,
                "price_eur": 95000,
            }
        ],
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
    # Lead name should contain the object name
    lead_arg = kommo.create_lead.await_args.args[0]
    assert "Sunset" in lead_arg.name
    assert "1+1" in lead_arg.name
    kommo.link_contact_to_lead.assert_awaited_once_with(200, 100)
    kommo.add_note.assert_awaited_once()
    note_text = kommo.add_note.await_args.args[2]
    assert "Sunset" in note_text
    assert "ID: prop-1" in note_text
    kommo.create_task.assert_awaited_once()
    # Task text should contain the object name
    task_arg = kommo.create_task.await_args.args[0]
    assert "Sunset" in task_arg.text
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
    manager.done.assert_awaited_once()
