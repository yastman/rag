"""Tests for CRM card callback handlers (#697 Task 8 / migrated #2053).

After #2053 the custom FSM (``state.set_state`` + ``StateFilter`` message
handlers) was replaced by an aiogram-dialog ``CrmQuickActionsDialog``. This
module now hosts only the callback-query trigger handlers, which start the
dialog via ``dialog_manager.start(state, data=..., mode=RESET_STACK)``. Tests
for the former message handlers (``on_note_text_received``,
``on_task_text_received``, ``on_edit_field_chosen``,
``on_edit_task_text_received``, ``on_edit_task_date_received``) live in
``tests/unit/dialogs/test_crm_quick_actions.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# --- Router creation ---


def test_create_crm_router_returns_router():
    """create_crm_router() returns an aiogram Router named 'crm_callbacks'."""
    from aiogram import Router

    from telegram_bot.handlers.crm_callbacks import create_crm_router

    router = create_crm_router()
    assert isinstance(router, Router)
    assert router.name == "crm_callbacks"


# --- FSM states still defined centrally in dialogs/states.py ---


def test_crm_quick_action_states_exist():
    """CrmQuickActionSG retains the five states used by the dialog."""
    from telegram_bot.dialogs.states import CrmQuickActionSG

    assert hasattr(CrmQuickActionSG, "waiting_note")
    assert hasattr(CrmQuickActionSG, "waiting_task")
    assert hasattr(CrmQuickActionSG, "edit_task_choose_field")
    assert hasattr(CrmQuickActionSG, "edit_task_text")
    assert hasattr(CrmQuickActionSG, "edit_task_date")


# --- Callback handlers: immediate actions (no dialog required) ---


@pytest.mark.asyncio
async def test_task_complete_calls_kommo():
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    kommo = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:complete:42"
    callback.message = AsyncMock()

    await on_task_complete(callback, kommo_client=kommo)

    kommo.complete_task.assert_awaited_once_with(42)
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_task_complete_no_kommo_answers_alert():
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    callback = AsyncMock()
    callback.data = "crm:task:complete:5"

    await on_task_complete(callback, kommo_client=None)

    callback.answer.assert_awaited_once()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_task_postpone_calls_kommo_update_task():
    from telegram_bot.handlers.crm_callbacks import on_task_postpone
    from telegram_bot.services.kommo_models import TaskUpdate

    kommo = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:postpone:7"
    callback.message = AsyncMock()

    await on_task_postpone(callback, kommo_client=kommo)

    kommo.update_task.assert_awaited_once()
    args = kommo.update_task.call_args.args
    assert args[0] == 7
    assert isinstance(args[1], TaskUpdate)
    assert args[1].complete_till is not None
    assert args[1].complete_till > 0


@pytest.mark.asyncio
async def test_task_postpone_no_kommo_answers_alert():
    from telegram_bot.handlers.crm_callbacks import on_task_postpone

    callback = AsyncMock()
    callback.data = "crm:task:postpone:5"

    await on_task_postpone(callback, kommo_client=None)

    callback.answer.assert_awaited_once()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


# --- Callback handlers: dialog-triggering ---


def _dialog_manager_mock() -> MagicMock:
    manager = MagicMock()
    manager.start = AsyncMock()
    return manager


@pytest.mark.asyncio
async def test_lead_note_starts_dialog_with_leads_entity():
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_lead_note

    kommo = AsyncMock()
    manager = _dialog_manager_mock()
    callback = AsyncMock()
    callback.data = "crm:lead:note:99"

    await on_lead_note(callback, manager, kommo_client=kommo)

    manager.start.assert_awaited_once()
    args = manager.start.call_args
    assert args.args[0] is CrmQuickActionSG.waiting_note
    assert args.kwargs["data"] == {"entity_type": "leads", "entity_id": 99}
    assert args.kwargs["mode"] is StartMode.RESET_STACK
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_lead_note_no_kommo_answers_alert_no_dialog():
    from telegram_bot.handlers.crm_callbacks import on_lead_note

    manager = _dialog_manager_mock()
    callback = AsyncMock()
    callback.data = "crm:lead:note:1"

    await on_lead_note(callback, manager, kommo_client=None)

    callback.answer.assert_awaited_once()
    assert callback.answer.call_args.kwargs.get("show_alert") is True
    manager.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_lead_task_starts_dialog_with_task_state():
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_lead_task

    kommo = AsyncMock()
    manager = _dialog_manager_mock()
    callback = AsyncMock()
    callback.data = "crm:lead:task:55"

    await on_lead_task(callback, manager, kommo_client=kommo)

    manager.start.assert_awaited_once()
    args = manager.start.call_args
    assert args.args[0] is CrmQuickActionSG.waiting_task
    assert args.kwargs["data"] == {"entity_type": "leads", "entity_id": 55}


@pytest.mark.asyncio
async def test_contact_note_starts_dialog_with_contacts_entity():
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_contact_note

    kommo = AsyncMock()
    manager = _dialog_manager_mock()
    callback = AsyncMock()
    callback.data = "crm:contact:note:12"

    await on_contact_note(callback, manager, kommo_client=kommo)

    manager.start.assert_awaited_once()
    args = manager.start.call_args
    assert args.args[0] is CrmQuickActionSG.waiting_note
    assert args.kwargs["data"] == {"entity_type": "contacts", "entity_id": 12}


@pytest.mark.asyncio
async def test_task_edit_starts_field_choice_dialog():
    from telegram_bot.dialogs.states import CrmQuickActionSG
    from telegram_bot.handlers.crm_callbacks import on_task_edit

    kommo = AsyncMock()
    manager = _dialog_manager_mock()
    callback = AsyncMock()
    callback.data = "crm:task:edit:42"

    await on_task_edit(callback, manager, kommo_client=kommo)

    manager.start.assert_awaited_once()
    args = manager.start.call_args
    assert args.args[0] is CrmQuickActionSG.edit_task_choose_field
    assert args.kwargs["data"] == {"edit_task_id": 42}


@pytest.mark.asyncio
async def test_task_edit_no_kommo_answers_alert_no_dialog():
    from telegram_bot.handlers.crm_callbacks import on_task_edit

    manager = _dialog_manager_mock()
    callback = AsyncMock()
    callback.data = "crm:task:edit:5"

    await on_task_edit(callback, manager, kommo_client=None)

    callback.answer.assert_awaited_once()
    assert callback.answer.call_args.kwargs.get("show_alert") is True
    manager.start.assert_not_awaited()


# --- crm_cards.py: postpone button (kept for parity, not affected by #2053) ---


def test_format_task_card_active_task_has_postpone_button():
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
    from telegram_bot.dialogs.crm_cards import format_task_card
    from telegram_bot.services.kommo_models import Task

    task = Task(id=4, text="Done task", is_completed=True)
    _, keyboard = format_task_card(task)

    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert not any("postpone" in cb for cb in all_callbacks)


# --------------------------------------------------------------------------
# @observe instrumentation (#1664 + #2053)
# --------------------------------------------------------------------------


class TestCrmCallbacksObserveInstrumentation:
    """Trigger-side @observe spans must remain intact after the #2053
    migration. Message-handler spans (``crm-quick-note``, ``crm-task-create``,
    ``crm-task-edit-text``, ``crm-task-edit-date``, ``crm-task-edit-field``)
    moved to the dialog module — they are checked there.
    """

    EXPECTED_CALLBACK_SPAN_NAMES = {
        "crm-lead-note-prompt",
        "crm-lead-task-prompt",
        "crm-task-postpone",
        "crm-contact-note-prompt",
        "crm-task-edit-prompt",
        "crm-quick-complete",
    }

    @staticmethod
    def _patched_lf(monkeypatch):
        """Replace get_client used by crm_callbacks module with a recording mock."""
        from telegram_bot.handlers import crm_callbacks as cb_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(cb_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe(monkeypatch):
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(*args, **kwargs):
            def decorator(func):
                return func

            if args and callable(args[0]) and not kwargs:
                return args[0]
            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        sys.modules.pop("telegram_bot.handlers.crm_callbacks", None)
        importlib.import_module("telegram_bot.handlers.crm_callbacks")

    def test_crm_callbacks_module_imports_observe_and_get_client(self):
        from telegram_bot.handlers import crm_callbacks as cb_mod

        assert hasattr(cb_mod, "observe")
        assert hasattr(cb_mod, "get_client")

    def test_crm_callbacks_observe_decorator_applied_with_correct_kwargs(self, monkeypatch):
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        captured: list[dict] = []

        def recording_observe(*args, **kwargs):
            captured.append(dict(kwargs))

            def decorator(func):
                return func

            if args and callable(args[0]) and not kwargs:
                return args[0]
            return decorator

        monkeypatch.setattr(observability_mod, "observe", recording_observe)
        sys.modules.pop("telegram_bot.handlers.crm_callbacks", None)
        importlib.import_module("telegram_bot.handlers.crm_callbacks")

        names = {entry.get("name") for entry in captured}
        missing = self.EXPECTED_CALLBACK_SPAN_NAMES - names
        assert not missing, (
            "Missing @observe spans on trigger-side crm_callbacks: "
            f"{sorted(missing)}. Captured: {sorted(n for n in names if n)}"
        )
        for entry in captured:
            name = entry.get("name")
            if name not in self.EXPECTED_CALLBACK_SPAN_NAMES:
                continue
            assert entry.get("capture_input") is False
            assert entry.get("capture_output") is False

    @pytest.mark.asyncio
    async def test_callback_prompt_works_when_langfuse_client_unavailable(self, monkeypatch):
        self._disable_observe(monkeypatch)
        from telegram_bot.handlers import crm_callbacks as cb_mod
        from telegram_bot.handlers.crm_callbacks import on_lead_note

        monkeypatch.setattr(cb_mod, "get_client", lambda: None)

        callback = AsyncMock()
        callback.data = "crm:lead:note:123"
        manager = _dialog_manager_mock()

        await on_lead_note(callback, manager, kommo_client=None)

        callback.answer.assert_awaited_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True
        manager.start.assert_not_awaited()
