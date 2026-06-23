"""Tests for the CRM quick actions aiogram-dialog (#2053).

Migrates the custom FSM in `telegram_bot/handlers/crm_callbacks.py` into a
proper aiogram-dialog Dialog using `MessageInput` widgets for free-text entry
and `Select` for the edit-field picker. Behavior parity (Kommo write safety,
empty/whitespace guards, invalid-date guard, no-Kommo guard) is preserved.

This is the first project usage of `MessageInput` for a CRM write flow, so the
contract here is treated as canonical. See also `docs/engineering/sdk-registry.md`
(aiogram-dialog section).
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ContentType

from telegram_bot.dialogs.states import CrmQuickActionSG


# ---------------------------------------------------------------------------
# Dialog structure
# ---------------------------------------------------------------------------


def test_crm_quick_actions_dialog_covers_all_five_states() -> None:
    from telegram_bot.dialogs.crm_quick_actions import crm_quick_actions_dialog

    expected = {
        CrmQuickActionSG.waiting_note,
        CrmQuickActionSG.waiting_task,
        CrmQuickActionSG.edit_task_choose_field,
        CrmQuickActionSG.edit_task_text,
        CrmQuickActionSG.edit_task_date,
    }
    assert set(crm_quick_actions_dialog.windows) == expected


def _window_message_inputs(window):
    """Return the MessageInput widgets registered on the given Window.

    aiogram-dialog stores ``window.on_message`` as the ``MessageInput`` directly
    when only one is registered, and as a ``CombinedInput`` wrapper exposing
    ``.inputs`` when multiple are registered. Handle both shapes.
    """
    from aiogram_dialog.widgets.input import MessageInput

    on_message = getattr(window, "on_message", None)
    if on_message is None:
        return []
    if isinstance(on_message, MessageInput):
        return [on_message]
    inputs = getattr(on_message, "inputs", None) or ()
    return [w for w in inputs if isinstance(w, MessageInput)]


@pytest.mark.parametrize(
    "state",
    [
        CrmQuickActionSG.waiting_note,
        CrmQuickActionSG.waiting_task,
        CrmQuickActionSG.edit_task_text,
        CrmQuickActionSG.edit_task_date,
    ],
)
def test_text_entry_windows_use_message_input_with_content_type_text(state) -> None:
    from telegram_bot.dialogs.crm_quick_actions import crm_quick_actions_dialog

    window = crm_quick_actions_dialog.windows[state]
    inputs = _window_message_inputs(window)
    assert inputs, f"Window {state} must register a MessageInput"
    # MessageInput stores content_types as a MagicFilter on `.filters`. A
    # non-empty filter list proves content_types was specified (we pass
    # [ContentType.TEXT] in the dialog). We verify the filter accepts a
    # text message but rejects non-text by simulating the filter call.
    mi = inputs[0]
    assert mi.filters, "MessageInput must restrict by content_type"
    # Behavioural check: TEXT passes the filter, PHOTO does not.

    class _FakeMessage:
        def __init__(self, content_type):
            self.content_type = content_type

    text_ok = all(f.callback(_FakeMessage(ContentType.TEXT)) for f in mi.filters)
    photo_ok = all(f.callback(_FakeMessage(ContentType.PHOTO)) for f in mi.filters)
    assert text_ok, f"Window {state} MessageInput must accept ContentType.TEXT"
    assert not photo_ok, f"Window {state} MessageInput must reject non-TEXT content"


def test_edit_field_window_uses_select_widget_no_message_input() -> None:
    """The field picker is the canonical Select usage for this dialog."""
    from aiogram_dialog.widgets.kbd import Select

    from telegram_bot.dialogs.crm_quick_actions import crm_quick_actions_dialog

    window = crm_quick_actions_dialog.windows[CrmQuickActionSG.edit_task_choose_field]
    # Walk the keyboard tree for any Select widget.
    found_select = False

    def _walk(widget):
        nonlocal found_select
        if isinstance(widget, Select):
            found_select = True
            return
        for child in getattr(widget, "buttons", None) or []:
            _walk(child)

    for widget in window.keyboard.buttons:
        _walk(widget)
    assert found_select, "edit_task_choose_field window must use a Select widget"
    # And no MessageInput on this window — choice is via inline buttons only.
    assert not _window_message_inputs(window)


# ---------------------------------------------------------------------------
# on_dialog_start: copy start_data into dialog_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_dialog_start_copies_start_data_into_dialog_data() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_dialog_start

    manager = MagicMock()
    manager.dialog_data = {}

    await on_dialog_start({"entity_type": "leads", "entity_id": 99}, manager)

    assert manager.dialog_data["entity_type"] == "leads"
    assert manager.dialog_data["entity_id"] == 99


@pytest.mark.asyncio
async def test_on_dialog_start_copies_edit_task_id() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_dialog_start

    manager = MagicMock()
    manager.dialog_data = {}

    await on_dialog_start({"edit_task_id": 42}, manager)

    assert manager.dialog_data["edit_task_id"] == 42


@pytest.mark.asyncio
async def test_on_dialog_start_handles_none_data_safely() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_dialog_start

    manager = MagicMock()
    manager.dialog_data = {}

    await on_dialog_start(None, manager)

    assert manager.dialog_data == {}


# ---------------------------------------------------------------------------
# Note text handler
# ---------------------------------------------------------------------------


def _make_manager(dialog_data: dict, kommo_client=None) -> MagicMock:
    manager = MagicMock()
    manager.dialog_data = dict(dialog_data)
    manager.middleware_data = {"kommo_client": kommo_client}
    manager.done = AsyncMock()
    return manager


@pytest.mark.asyncio
async def test_on_note_text_input_calls_add_note_and_closes_dialog() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_note_text_input

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"entity_type": "leads", "entity_id": 10},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "Client called back"

    await on_note_text_input(message, MagicMock(), manager)

    kommo.add_note.assert_awaited_once_with("leads", 10, "Client called back")
    manager.done.assert_awaited_once()
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_on_note_text_input_contacts_entity_type() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_note_text_input

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"entity_type": "contacts", "entity_id": 5},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "Contact note"

    await on_note_text_input(message, MagicMock(), manager)

    kommo.add_note.assert_awaited_once_with("contacts", 5, "Contact note")


@pytest.mark.asyncio
async def test_on_note_text_input_empty_message_warns_no_add() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_note_text_input

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"entity_type": "leads", "entity_id": 10},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "   "

    await on_note_text_input(message, MagicMock(), manager)

    kommo.add_note.assert_not_called()
    manager.done.assert_not_called()
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_on_note_text_input_no_kommo_client_closes_dialog() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_note_text_input

    manager = _make_manager(
        dialog_data={"entity_type": "leads", "entity_id": 10},
        kommo_client=None,
    )
    message = AsyncMock()
    message.text = "Some note"

    await on_note_text_input(message, MagicMock(), manager)

    manager.done.assert_awaited_once()
    message.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Task text handler (create_task)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_task_text_input_creates_task_with_due_date_plus_one_day() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_task_text_input
    from telegram_bot.services.kommo_models import TaskCreate

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"entity_type": "leads", "entity_id": 20},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "Follow up"

    before = datetime.datetime.now(datetime.UTC).timestamp()
    await on_task_text_input(message, MagicMock(), manager)
    after = datetime.datetime.now(datetime.UTC).timestamp()

    kommo.create_task.assert_awaited_once()
    task_arg = kommo.create_task.call_args.args[0]
    assert isinstance(task_arg, TaskCreate)
    assert task_arg.text == "Follow up"
    assert task_arg.entity_id == 20
    # +1 day from now (with a little slack for execution time)
    assert before + 86400 - 5 <= task_arg.complete_till <= after + 86400 + 5
    manager.done.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_task_text_input_empty_warns_no_create() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_task_text_input

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"entity_type": "leads", "entity_id": 20},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = ""

    await on_task_text_input(message, MagicMock(), manager)

    kommo.create_task.assert_not_called()
    manager.done.assert_not_called()
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_on_task_text_input_no_kommo_closes_dialog() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_task_text_input

    manager = _make_manager(
        dialog_data={"entity_type": "leads", "entity_id": 20},
        kommo_client=None,
    )
    message = AsyncMock()
    message.text = "Task text"

    await on_task_text_input(message, MagicMock(), manager)

    manager.done.assert_awaited_once()
    message.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Edit-field Select handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_edit_field_select_text_switches_to_edit_text_state() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_field_select

    manager = MagicMock()
    manager.switch_to = AsyncMock()
    manager.dialog_data = {}

    await on_edit_field_select(MagicMock(), MagicMock(), manager, "text")

    manager.switch_to.assert_awaited_once_with(CrmQuickActionSG.edit_task_text)


@pytest.mark.asyncio
async def test_on_edit_field_select_date_switches_to_edit_date_state() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_field_select

    manager = MagicMock()
    manager.switch_to = AsyncMock()
    manager.dialog_data = {}

    await on_edit_field_select(MagicMock(), MagicMock(), manager, "date")

    manager.switch_to.assert_awaited_once_with(CrmQuickActionSG.edit_task_date)


# ---------------------------------------------------------------------------
# Edit task text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_edit_task_text_input_updates_via_kommo() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_task_text_input
    from telegram_bot.services.kommo_models import TaskUpdate

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"edit_task_id": 77},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "New text"

    await on_edit_task_text_input(message, MagicMock(), manager)

    kommo.update_task.assert_awaited_once()
    args = kommo.update_task.call_args.args
    assert args[0] == 77
    assert isinstance(args[1], TaskUpdate)
    assert args[1].text == "New text"
    manager.done.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_edit_task_text_input_empty_warns_no_update() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_task_text_input

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"edit_task_id": 77},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "   "

    await on_edit_task_text_input(message, MagicMock(), manager)

    kommo.update_task.assert_not_called()
    manager.done.assert_not_called()
    message.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Edit task date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_edit_task_date_input_parses_and_updates() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_task_date_input
    from telegram_bot.services.kommo_models import TaskUpdate

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"edit_task_id": 55},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "31.12.2027 10:00"

    await on_edit_task_date_input(message, MagicMock(), manager)

    kommo.update_task.assert_awaited_once()
    args = kommo.update_task.call_args.args
    assert args[0] == 55
    assert isinstance(args[1], TaskUpdate)
    expected_ts = int(datetime.datetime(2027, 12, 31, 10, 0, tzinfo=datetime.UTC).timestamp())
    assert args[1].complete_till == expected_ts
    manager.done.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_edit_task_date_input_invalid_format_warns_no_update() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_task_date_input

    kommo = AsyncMock()
    manager = _make_manager(
        dialog_data={"edit_task_id": 55},
        kommo_client=kommo,
    )
    message = AsyncMock()
    message.text = "not-a-date"

    await on_edit_task_date_input(message, MagicMock(), manager)

    kommo.update_task.assert_not_called()
    manager.done.assert_not_called()
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_on_edit_task_date_input_no_kommo_closes_dialog() -> None:
    from telegram_bot.dialogs.crm_quick_actions import on_edit_task_date_input

    manager = _make_manager(
        dialog_data={"edit_task_id": 55},
        kommo_client=None,
    )
    message = AsyncMock()
    message.text = "31.12.2027 10:00"

    await on_edit_task_date_input(message, MagicMock(), manager)

    manager.done.assert_awaited_once()
    message.answer.assert_awaited()


# ---------------------------------------------------------------------------
# Edit-field options getter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_edit_field_options_lists_text_and_date_choices() -> None:
    from telegram_bot.dialogs.crm_quick_actions import get_edit_field_options

    data = await get_edit_field_options(MagicMock())

    items = data["items"]
    ids = [item[1] for item in items]
    assert ids == ["text", "date"]
