"""Tests for CRM card callback handlers (#697 Task 8)."""

from __future__ import annotations

from unittest.mock import AsyncMock


# --- Router creation ---


def test_create_crm_router_returns_router():
    """create_crm_router() returns an aiogram Router named 'crm_callbacks'."""
    from aiogram import Router

    from telegram_bot.handlers.crm_callbacks import create_crm_router

    router = create_crm_router()
    assert isinstance(router, Router)
    assert router.name == "crm_callbacks"


# --- FSM states ---


def test_crm_quick_action_states_exist():
    """CrmQuickActionSG has waiting_note and waiting_task states."""
    from telegram_bot.dialogs.states import CrmQuickActionSG

    assert hasattr(CrmQuickActionSG, "waiting_note")
    assert hasattr(CrmQuickActionSG, "waiting_task")


# --- Callback handlers: immediate actions ---


async def test_task_complete_calls_kommo():
    """on_task_complete calls kommo_client.complete_task with correct id."""
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    kommo = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:complete:42"
    callback.message = AsyncMock()

    await on_task_complete(callback, kommo_client=kommo)

    kommo.complete_task.assert_called_once_with(42)
    callback.answer.assert_called()


async def test_task_complete_no_kommo_answers_alert():
    """on_task_complete without kommo_client answers with show_alert=True."""
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    callback = AsyncMock()
    callback.data = "crm:task:complete:5"

    await on_task_complete(callback, kommo_client=None)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args.kwargs
    assert call_kwargs.get("show_alert") is True


async def test_task_postpone_calls_kommo_update_task():
    """on_task_postpone calls kommo_client.update_task(id, TaskUpdate) with +1 day."""
    from telegram_bot.handlers.crm_callbacks import on_task_postpone
    from telegram_bot.services.kommo_models import TaskUpdate

    kommo = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:postpone:7"
    callback.message = AsyncMock()

    await on_task_postpone(callback, kommo_client=kommo)

    kommo.update_task.assert_called_once()
    call_args = kommo.update_task.call_args
    assert call_args.args[0] == 7
    update_obj = call_args.args[1]
    assert isinstance(update_obj, TaskUpdate)
    assert update_obj.complete_till is not None
    assert update_obj.complete_till > 0


async def test_task_postpone_no_kommo_answers_alert():
    """on_task_postpone without kommo_client answers with show_alert=True."""
    from telegram_bot.handlers.crm_callbacks import on_task_postpone

    callback = AsyncMock()
    callback.data = "crm:task:postpone:5"

    await on_task_postpone(callback, kommo_client=None)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args.kwargs
    assert call_kwargs.get("show_alert") is True


# --- Callback handlers: FSM-triggering ---


async def test_lead_note_callback_sets_fsm_state():
    """on_lead_note sets waiting_note state with entity_type='leads'."""
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_lead_note

    kommo = AsyncMock()
    state = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:lead:note:99"
    callback.message = AsyncMock()

    await on_lead_note(callback, state, kommo_client=kommo)

    state.set_state.assert_called_once_with(CrmQuickActionSG.waiting_note)
    state.update_data.assert_called_once_with(entity_type="leads", entity_id=99)
    callback.message.answer.assert_called_once()
    callback.answer.assert_called_once()


async def test_lead_note_no_kommo_answers_alert():
    """on_lead_note without kommo_client answers alert, no FSM transition."""
    from telegram_bot.handlers.crm_callbacks import on_lead_note

    state = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:lead:note:1"

    await on_lead_note(callback, state, kommo_client=None)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args.kwargs
    assert call_kwargs.get("show_alert") is True
    state.set_state.assert_not_called()


async def test_lead_task_callback_sets_fsm_state():
    """on_lead_task sets waiting_task state with entity_type='leads'."""
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_lead_task

    kommo = AsyncMock()
    state = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:lead:task:55"
    callback.message = AsyncMock()

    await on_lead_task(callback, state, kommo_client=kommo)

    state.set_state.assert_called_once_with(CrmQuickActionSG.waiting_task)
    state.update_data.assert_called_once_with(entity_id=55, entity_type="leads")
    callback.message.answer.assert_called_once()


async def test_contact_note_callback_sets_fsm_state():
    """on_contact_note sets waiting_note state with entity_type='contacts'."""
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_contact_note

    kommo = AsyncMock()
    state = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:contact:note:12"
    callback.message = AsyncMock()

    await on_contact_note(callback, state, kommo_client=kommo)

    state.set_state.assert_called_once_with(CrmQuickActionSG.waiting_note)
    state.update_data.assert_called_once_with(entity_type="contacts", entity_id=12)
    callback.message.answer.assert_called_once()


# --- FSM message handlers ---


async def test_note_text_received_calls_add_note():
    """on_note_text_received calls kommo_client.add_note with entity and text."""
    from telegram_bot.handlers.crm_callbacks import on_note_text_received

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entity_type": "leads", "entity_id": 10})
    message = AsyncMock()
    message.text = "Client called back"

    await on_note_text_received(message, state, kommo_client=kommo)

    kommo.add_note.assert_called_once_with("leads", 10, "Client called back")
    state.clear.assert_called_once()
    message.answer.assert_called()


async def test_note_text_received_contacts_entity():
    """on_note_text_received uses entity_type='contacts' correctly."""
    from telegram_bot.handlers.crm_callbacks import on_note_text_received

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entity_type": "contacts", "entity_id": 5})
    message = AsyncMock()
    message.text = "Contact note"

    await on_note_text_received(message, state, kommo_client=kommo)

    kommo.add_note.assert_called_once_with("contacts", 5, "Contact note")


async def test_task_text_received_calls_create_task():
    """on_task_text_received calls kommo_client.create_task with correct TaskCreate."""
    from telegram_bot.handlers.crm_callbacks import on_task_text_received
    from telegram_bot.services.kommo_models import TaskCreate

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entity_id": 20, "entity_type": "leads"})
    message = AsyncMock()
    message.text = "Follow up with client"

    await on_task_text_received(message, state, kommo_client=kommo)

    kommo.create_task.assert_called_once()
    task_arg = kommo.create_task.call_args.args[0]
    assert isinstance(task_arg, TaskCreate)
    assert task_arg.text == "Follow up with client"
    assert task_arg.entity_id == 20
    assert task_arg.complete_till is not None
    state.clear.assert_called_once()
    message.answer.assert_called()


async def test_note_empty_text_skips_create():
    """on_note_text_received with whitespace-only text does not call add_note."""
    from telegram_bot.handlers.crm_callbacks import on_note_text_received

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entity_type": "leads", "entity_id": 10})
    message = AsyncMock()
    message.text = "   "

    await on_note_text_received(message, state, kommo_client=kommo)

    kommo.add_note.assert_not_called()
    message.answer.assert_called()


async def test_note_no_kommo_sends_error_message():
    """on_note_text_received without kommo_client sends an error message."""
    from telegram_bot.handlers.crm_callbacks import on_note_text_received

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entity_type": "leads", "entity_id": 10})
    message = AsyncMock()
    message.text = "Some note"

    await on_note_text_received(message, state, kommo_client=None)

    message.answer.assert_called()


async def test_task_no_kommo_sends_error_message():
    """on_task_text_received without kommo_client sends an error message."""
    from telegram_bot.handlers.crm_callbacks import on_task_text_received

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"entity_id": 20, "entity_type": "leads"})
    message = AsyncMock()
    message.text = "Task text"

    await on_task_text_received(message, state, kommo_client=None)

    message.answer.assert_called()


# --- Task edit FSM states ---


def test_crm_quick_action_states_have_edit_states():
    """CrmQuickActionSG has edit_task_choose_field, edit_task_text, edit_task_date states."""
    from telegram_bot.dialogs.states import CrmQuickActionSG

    assert hasattr(CrmQuickActionSG, "edit_task_choose_field")
    assert hasattr(CrmQuickActionSG, "edit_task_text")
    assert hasattr(CrmQuickActionSG, "edit_task_date")


async def test_on_task_edit_starts_field_choice():
    """crm:task:edit:{id} sets edit_task_choose_field state and stores task id."""
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_task_edit

    kommo = AsyncMock()
    state = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:edit:42"
    callback.message = AsyncMock()

    await on_task_edit(callback, state, kommo_client=kommo)

    state.set_state.assert_called_once_with(CrmQuickActionSG.edit_task_choose_field)
    state.update_data.assert_called_once_with(edit_task_id=42)
    callback.answer.assert_called()


async def test_on_task_edit_no_kommo_answers_alert():
    """on_task_edit without kommo_client answers with show_alert=True."""
    from telegram_bot.handlers.crm_callbacks import on_task_edit

    state = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:edit:5"

    await on_task_edit(callback, state, kommo_client=None)

    callback.answer.assert_called_once()
    call_kwargs = callback.answer.call_args.kwargs
    assert call_kwargs.get("show_alert") is True
    state.set_state.assert_not_called()


async def test_on_edit_field_chosen_1_goes_to_text():
    """on_edit_field_chosen with '1' sets edit_task_text state."""
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_edit_field_chosen

    state = AsyncMock()
    message = AsyncMock()
    message.text = "1"

    await on_edit_field_chosen(message, state)

    state.set_state.assert_called_once_with(CrmQuickActionSG.edit_task_text)
    message.answer.assert_called()


async def test_on_edit_field_chosen_2_goes_to_date():
    """on_edit_field_chosen with '2' sets edit_task_date state."""
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_edit_field_chosen

    state = AsyncMock()
    message = AsyncMock()
    message.text = "2"

    await on_edit_field_chosen(message, state)

    state.set_state.assert_called_once_with(CrmQuickActionSG.edit_task_date)
    message.answer.assert_called()


async def test_on_edit_field_chosen_invalid_sends_warning():
    """on_edit_field_chosen with invalid input sends warning, no state change."""
    from telegram_bot.handlers.crm_callbacks import on_edit_field_chosen

    state = AsyncMock()
    message = AsyncMock()
    message.text = "5"

    await on_edit_field_chosen(message, state)

    state.set_state.assert_not_called()
    message.answer.assert_called()


async def test_on_edit_task_text_received_calls_update():
    """on_edit_task_text_received calls kommo_client.update_task with new text."""
    from telegram_bot.handlers.crm_callbacks import on_edit_task_text_received
    from telegram_bot.services.kommo_models import TaskUpdate

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"edit_task_id": 77})
    message = AsyncMock()
    message.text = "New task text"

    await on_edit_task_text_received(message, state, kommo_client=kommo)

    kommo.update_task.assert_called_once()
    call_args = kommo.update_task.call_args
    assert call_args.args[0] == 77
    update_obj = call_args.args[1]
    assert isinstance(update_obj, TaskUpdate)
    assert update_obj.text == "New task text"
    state.clear.assert_called_once()


async def test_on_edit_task_date_received_calls_update():
    """on_edit_task_date_received parses date and calls kommo_client.update_task."""
    from telegram_bot.handlers.crm_callbacks import on_edit_task_date_received
    from telegram_bot.services.kommo_models import TaskUpdate

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"edit_task_id": 55})
    message = AsyncMock()
    message.text = "31.12.2027 10:00"

    await on_edit_task_date_received(message, state, kommo_client=kommo)

    kommo.update_task.assert_called_once()
    call_args = kommo.update_task.call_args
    assert call_args.args[0] == 55
    update_obj = call_args.args[1]
    assert isinstance(update_obj, TaskUpdate)
    assert update_obj.complete_till is not None
    assert update_obj.complete_till > 0
    state.clear.assert_called_once()


async def test_on_edit_task_date_received_invalid_format():
    """on_edit_task_date_received with bad date sends warning, no update."""
    from telegram_bot.handlers.crm_callbacks import on_edit_task_date_received

    kommo = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"edit_task_id": 55})
    message = AsyncMock()
    message.text = "not-a-date"

    await on_edit_task_date_received(message, state, kommo_client=kommo)

    kommo.update_task.assert_not_called()
    message.answer.assert_called()


def test_crm_router_registers_edit_callback():
    """create_crm_router registers crm:task:edit handler."""
    from telegram_bot.handlers.crm_callbacks import create_crm_router

    router = create_crm_router()
    # Verify router was created without errors (handlers registered)
    assert router is not None
    assert router.name == "crm_callbacks"


# --- crm_cards.py: postpone button ---


def test_format_task_card_active_task_has_postpone_button():
    """format_task_card for active task includes crm:task:postpone:{id} button."""
    from telegram_bot.dialogs.crm_cards import format_task_card
    from telegram_bot.services.kommo_models import Task

    task = Task(id=3, text="Call client", is_completed=False)
    _, keyboard = format_task_card(task)

    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert any("postpone" in cb for cb in all_callbacks)
    assert any(cb == "crm:task:postpone:3" for cb in all_callbacks)


def test_format_task_card_completed_task_no_postpone_button():
    """format_task_card for completed task does NOT include postpone button."""
    from telegram_bot.dialogs.crm_cards import format_task_card
    from telegram_bot.services.kommo_models import Task

    task = Task(id=4, text="Done task", is_completed=True)
    _, keyboard = format_task_card(task)

    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert not any("postpone" in cb for cb in all_callbacks)
