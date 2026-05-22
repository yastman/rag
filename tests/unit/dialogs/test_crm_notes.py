"""Tests for CRM note wizard dialog (#697) — Task 7."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


# --- Dialog object export ---


def test_create_note_dialog_exported():
    """crm_notes module exports create_note_dialog."""
    from telegram_bot.dialogs import crm_notes

    assert hasattr(crm_notes, "create_note_dialog")


def test_create_note_dialog_is_dialog():
    """create_note_dialog is an aiogram-dialog Dialog instance."""
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.crm_notes import create_note_dialog

    assert isinstance(create_note_dialog, Dialog)


# --- CreateNoteSG states ---


def test_create_note_sg_has_text_state():
    """CreateNoteSG has 'text' state (first step)."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "text")


def test_create_note_sg_has_entity_type_state():
    """CreateNoteSG has 'entity_type' state."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "entity_type")


def test_create_note_sg_has_entity_id_state():
    """CreateNoteSG has 'entity_id' state."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "entity_id")


def test_create_note_sg_has_summary_state():
    """CreateNoteSG has 'summary' state."""
    from telegram_bot.dialogs.states import CreateNoteSG

    assert hasattr(CreateNoteSG, "summary")


# --- Entity type options ---


def test_note_entity_type_options_exported():
    """crm_notes exports NOTE_ENTITY_TYPES constant."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    assert isinstance(NOTE_ENTITY_TYPES, list)
    assert len(NOTE_ENTITY_TYPES) >= 2


def test_note_entity_type_options_include_leads():
    """NOTE_ENTITY_TYPES includes leads option."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    keys = [item[1] for item in NOTE_ENTITY_TYPES]
    assert "leads" in keys


def test_note_entity_type_options_include_contacts():
    """NOTE_ENTITY_TYPES includes contacts option."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    keys = [item[1] for item in NOTE_ENTITY_TYPES]
    assert "contacts" in keys


def test_note_entity_type_options_are_tuples():
    """NOTE_ENTITY_TYPES items are (label, key) tuples."""
    from telegram_bot.dialogs.crm_notes import NOTE_ENTITY_TYPES

    for item in NOTE_ENTITY_TYPES:
        assert isinstance(item, tuple)
        assert len(item) == 2


# --- build_note_summary helper ---


def test_build_note_summary_leads():
    """build_note_summary formats note summary for lead attachment."""
    from telegram_bot.dialogs.crm_notes import build_note_summary

    result = build_note_summary(text="Client called", entity_type="leads", entity_id=42)

    assert "Client called" in result
    assert "42" in result


def test_build_note_summary_contacts():
    """build_note_summary formats note summary for contact attachment."""
    from telegram_bot.dialogs.crm_notes import build_note_summary

    result = build_note_summary(text="Note text", entity_type="contacts", entity_id=7)

    assert "Note text" in result
    assert "7" in result


def test_build_note_summary_no_entity():
    """build_note_summary handles no entity case."""
    from telegram_bot.dialogs.crm_notes import build_note_summary

    result = build_note_summary(text="General note", entity_type=None, entity_id=None)

    assert "General note" in result
    assert isinstance(result, str)


# --- Handlers ---


async def test_on_note_text_entered_strips_and_saves():
    """on_note_text_entered strips text, saves to dialog_data, switches to entity_type."""
    from telegram_bot.dialogs.crm_notes import on_note_text_entered
    from telegram_bot.dialogs.states import CreateNoteSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    message = MagicMock()
    widget = MagicMock()

    await on_note_text_entered(message, widget, dm, "  Some note text  ")

    assert dm.dialog_data["note_text"] == "Some note text"
    dm.switch_to.assert_awaited_once_with(CreateNoteSG.entity_type)


async def test_on_entity_type_selected_none():
    """on_entity_type_selected('none') stores type, clears entity_id, switches to summary."""
    from telegram_bot.dialogs.crm_notes import on_entity_type_selected
    from telegram_bot.dialogs.states import CreateNoteSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    callback = MagicMock()
    widget = MagicMock()

    await on_entity_type_selected(callback, widget, dm, "none")

    assert dm.dialog_data["entity_type"] == "none"
    assert dm.dialog_data["entity_id"] is None
    dm.switch_to.assert_awaited_once_with(CreateNoteSG.summary)


async def test_on_entity_type_selected_leads():
    """on_entity_type_selected('leads') stores type and switches to entity_id."""
    from telegram_bot.dialogs.crm_notes import on_entity_type_selected
    from telegram_bot.dialogs.states import CreateNoteSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    callback = MagicMock()
    widget = MagicMock()

    await on_entity_type_selected(callback, widget, dm, "leads")

    assert dm.dialog_data["entity_type"] == "leads"
    dm.switch_to.assert_awaited_once_with(CreateNoteSG.entity_id)


async def test_on_entity_selected_stores_id_and_switches_summary():
    """on_entity_selected stores entity_id and switches to summary."""
    from telegram_bot.dialogs.crm_notes import on_entity_selected
    from telegram_bot.dialogs.states import CreateNoteSG

    dm = MagicMock()
    dm.dialog_data = {}
    dm.switch_to = AsyncMock()

    callback = MagicMock()
    widget = MagicMock()

    await on_entity_selected(callback, widget, dm, "42")

    assert dm.dialog_data["entity_id"] == "42"
    dm.switch_to.assert_awaited_once_with(CreateNoteSG.summary)


# --- Getters ---


async def test_get_entity_options_mocked_leads():
    """get_entity_options returns leads from kommo_client."""
    from telegram_bot.dialogs.crm_notes import get_entity_options
    from telegram_bot.services.kommo_models import Lead

    fake_lead = Lead(id=5, name="Lead Alpha")
    kommo = AsyncMock()
    kommo.search_leads = AsyncMock(return_value=[fake_lead])

    dm = MagicMock()
    dm.dialog_data = {"entity_type": "leads"}
    dm.middleware_data = {"kommo_client": kommo}

    result = await get_entity_options(dialog_manager=dm)

    assert "Lead Alpha" in result["items"][0][0]
    assert result["items"][0][1] == "5"


async def test_get_entity_options_mocked_contacts():
    """get_entity_options returns contacts from kommo_client."""
    from telegram_bot.dialogs.crm_notes import get_entity_options
    from telegram_bot.services.kommo_models import Contact

    fake_contact = Contact(id=3, first_name="Ivan", last_name="Petrov")
    kommo = AsyncMock()
    kommo.get_contacts = AsyncMock(return_value=[fake_contact])

    dm = MagicMock()
    dm.dialog_data = {"entity_type": "contacts"}
    dm.middleware_data = {"kommo_client": kommo}

    result = await get_entity_options(dialog_manager=dm)

    assert "Ivan Petrov" in result["items"][0][0]
    assert result["items"][0][1] == "3"


async def test_get_entity_options_no_records_fallback():
    """get_entity_options falls back to placeholder when no records."""
    from telegram_bot.dialogs.crm_notes import get_entity_options

    dm = MagicMock()
    dm.dialog_data = {"entity_type": "leads"}
    dm.middleware_data = {}

    result = await get_entity_options(dialog_manager=dm)

    assert result["items"][0][1] == "0"
    assert "нет доступных записей" in result["items"][0][0]


async def test_get_note_summary_with_entity():
    """get_note_summary returns formatted summary with attached entity."""
    from telegram_bot.dialogs.crm_notes import get_note_summary

    dm = MagicMock()
    dm.dialog_data = {"note_text": "Call back", "entity_type": "leads", "entity_id": "7"}

    result = await get_note_summary(dialog_manager=dm)

    assert "Call back" in result["summary"]
    assert "7" in result["summary"]


async def test_get_note_summary_no_entity():
    """get_note_summary handles no-entity (none) case."""
    from telegram_bot.dialogs.crm_notes import get_note_summary

    dm = MagicMock()
    dm.dialog_data = {"note_text": "General note", "entity_type": "none", "entity_id": None}

    result = await get_note_summary(dialog_manager=dm)

    assert "General note" in result["summary"]
    assert "без привязки" in result["summary"]


# --- on_note_confirm ---


async def test_on_note_confirm_no_attachment():
    """on_note_confirm answers and closes when entity_type is none."""
    from telegram_bot.dialogs.crm_notes import on_note_confirm

    dm = MagicMock()
    dm.dialog_data = {"note_text": "Note", "entity_type": "none", "entity_id": None}
    dm.middleware_data = {}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.answer = AsyncMock()
    button = MagicMock()

    await on_note_confirm(callback, button, dm)

    callback.answer.assert_awaited_once()
    dm.done.assert_awaited_once()


async def test_on_note_confirm_missing_kommo():
    """on_note_confirm shows error when kommo client is missing."""
    from telegram_bot.dialogs.crm_notes import on_note_confirm

    dm = MagicMock()
    dm.dialog_data = {"note_text": "Note", "entity_type": "leads", "entity_id": "5"}
    dm.middleware_data = {}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.answer = AsyncMock()
    button = MagicMock()

    await on_note_confirm(callback, button, dm)

    callback.answer.assert_awaited_once_with("CRM недоступен", show_alert=True)
    dm.done.assert_awaited_once()


async def test_on_note_confirm_invalid_fields():
    """on_note_confirm shows error when fields are missing/invalid."""
    from telegram_bot.dialogs.crm_notes import on_note_confirm

    dm = MagicMock()
    dm.dialog_data = {"note_text": "", "entity_type": "leads", "entity_id": "0"}
    dm.middleware_data = {"kommo_client": AsyncMock()}

    callback = MagicMock()
    callback.answer = AsyncMock()
    button = MagicMock()

    await on_note_confirm(callback, button, dm)

    callback.answer.assert_awaited_once_with("Ошибка: не все поля заполнены", show_alert=True)


async def test_on_note_confirm_success():
    """on_note_confirm creates note via Kommo and answers with note id."""
    from telegram_bot.dialogs.crm_notes import on_note_confirm
    from telegram_bot.services.kommo_models import Note

    note = Note(id=99, text="Note text")
    kommo = AsyncMock()
    kommo.add_note = AsyncMock(return_value=note)

    dm = MagicMock()
    dm.dialog_data = {"note_text": "Note text", "entity_type": "leads", "entity_id": "5"}
    dm.middleware_data = {"kommo_client": kommo}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.answer = AsyncMock()
    button = MagicMock()

    await on_note_confirm(callback, button, dm)

    kommo.add_note.assert_awaited_once_with("leads", 5, "Note text")
    callback.answer.assert_awaited_once_with("📝 Заметка #99 создана!", show_alert=True)
    dm.done.assert_awaited_once()


async def test_on_note_confirm_exception():
    """on_note_confirm handles exception from Kommo API."""
    from telegram_bot.dialogs.crm_notes import on_note_confirm

    kommo = AsyncMock()
    kommo.add_note = AsyncMock(side_effect=Exception("kommo down"))

    dm = MagicMock()
    dm.dialog_data = {"note_text": "Note text", "entity_type": "leads", "entity_id": "5"}
    dm.middleware_data = {"kommo_client": kommo}
    dm.done = AsyncMock()

    callback = MagicMock()
    callback.answer = AsyncMock()
    button = MagicMock()

    await on_note_confirm(callback, button, dm)

    callback.answer.assert_awaited_once_with("❌ Ошибка при создании заметки", show_alert=True)
    dm.done.assert_awaited_once()
