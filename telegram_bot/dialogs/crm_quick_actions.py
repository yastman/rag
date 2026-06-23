"""CRM quick actions dialog (#2053).

Migrates the custom FSM from `telegram_bot/handlers/crm_callbacks.py` to
aiogram-dialog. Five windows mapped to the existing `CrmQuickActionSG`
states; text-entry windows use ``MessageInput`` (first project usage —
covered by focused tests) and the edit-field picker uses ``Select``.

Behavior parity with the previous custom FSM is preserved:

* Empty / whitespace-only text falls through with a user-visible warning.
* If ``kommo_client`` is unavailable, the dialog is closed gracefully with
  an error message — no Kommo write is attempted.
* Invalid date format on the edit-date window does not advance state.
* All write paths are observed via ``@observe`` for Langfuse trace parity.

Trigger callbacks (``crm:lead:note:{id}``, ``crm:lead:task:{id}``,
``crm:contact:note:{id}``, ``crm:task:edit:{id}``) live in
``telegram_bot/handlers/crm_callbacks.py`` and start this dialog via
``dialog_manager.start(...)`` instead of ``state.set_state(...)``.
"""

from __future__ import annotations

import datetime
import logging
import operator
import time
from typing import Any

from aiogram.enums import ContentType
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Cancel, Column, Select
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.observability import get_client, observe
from telegram_bot.services.kommo_models import TaskCreate, TaskUpdate

from .states import CrmQuickActionSG


logger = logging.getLogger(__name__)


# User-facing strings -------------------------------------------------------

_NOTE_PROMPT = "✏️ Введите текст заметки:"
_TASK_PROMPT = "✅ Введите текст задачи:"
_NOTE_SUCCESS = "✅ Заметка добавлена."
_TASK_SUCCESS = "✅ Задача создана."
_NO_CRM = "⚠️ CRM недоступна."
_EMPTY_NOTE_WARN = "⚠️ Текст заметки не может быть пустым."
_EMPTY_TASK_WARN = "⚠️ Текст задачи не может быть пустым."
_EMPTY_TEXT_WARN = "⚠️ Текст не может быть пустым."
_BAD_DATE_WARN = "⚠️ Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ"
_EDIT_FIELD_PROMPT = "✏️ Что изменить?"
_EDIT_TEXT_PROMPT = "📝 Введите новый текст задачи:"
_EDIT_DATE_PROMPT = "📅 Введите новый срок (ДД.ММ.ГГГГ ЧЧ:ММ):"
_EDIT_SUCCESS = "✅ Задача обновлена."

# Edit-field Select items: (label, item_id) — Select item_id_getter takes [1].
_EDIT_FIELD_ITEMS: list[tuple[str, str]] = [
    ("📝 Текст задачи", "text"),
    ("📅 Срок выполнения", "date"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _update_current_span(lf: Any, **kwargs: Any) -> None:
    """Update the current Langfuse span when tracing is available."""
    if lf is not None:
        lf.update_current_span(**kwargs)


def _kommo_from_manager(manager: DialogManager) -> Any | None:
    return manager.middleware_data.get("kommo_client")


# ---------------------------------------------------------------------------
# on_dialog_start: copy data passed in via dialog_manager.start(..., data=...)
# ---------------------------------------------------------------------------


async def on_dialog_start(start_data: Any, manager: DialogManager) -> None:
    """Copy known keys from start_data into dialog_data.

    Trigger callbacks pass ``{entity_type, entity_id}`` for note/task and
    ``{edit_task_id}`` for the task editor. Anything unrecognised is ignored.
    """
    if not isinstance(start_data, dict):
        return
    for key in ("entity_type", "entity_id", "edit_task_id"):
        if key in start_data:
            manager.dialog_data[key] = start_data[key]


# ---------------------------------------------------------------------------
# Note text handler — adds a note to a lead or contact
# ---------------------------------------------------------------------------


@observe(name="crm-quick-note", capture_input=False, capture_output=False)
async def on_note_text_input(
    message: Message,
    _widget: MessageInput,
    manager: DialogManager,
) -> None:
    lf = get_client()
    data = manager.dialog_data
    entity_type = str(data.get("entity_type", "leads"))
    entity_id = int(data.get("entity_id", 0) or 0)
    text = (message.text or "").strip()

    _update_current_span(lf, input={"deal_id": entity_id, "action": "create"})

    if not text:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_EMPTY_NOTE_WARN)
        return

    kommo = _kommo_from_manager(manager)
    if kommo is None:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_NO_CRM)
        await manager.done()
        return

    try:
        await kommo.add_note(entity_type, entity_id, text)
        await message.answer(_NOTE_SUCCESS)
    except Exception as exc:
        logger.exception("Failed to add note for %s #%d", entity_type, entity_id)
        _update_current_span(lf, level="ERROR", status_message=str(exc)[:200])
        await message.answer("⚠️ Ошибка при добавлении заметки.")
    finally:
        await manager.done()


# ---------------------------------------------------------------------------
# Task text handler — creates a task with due_date = now + 1d
# ---------------------------------------------------------------------------


@observe(name="crm-task-create", capture_input=False, capture_output=False)
async def on_task_text_input(
    message: Message,
    _widget: MessageInput,
    manager: DialogManager,
) -> None:
    lf = get_client()
    data = manager.dialog_data
    entity_id = int(data.get("entity_id", 0) or 0)
    text = (message.text or "").strip()

    _update_current_span(lf, input={"deal_id": entity_id, "action": "create"})

    if not text:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_EMPTY_TASK_WARN)
        return

    kommo = _kommo_from_manager(manager)
    if kommo is None:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_NO_CRM)
        await manager.done()
        return

    try:
        due_ts = int(time.time()) + 86400
        await kommo.create_task(TaskCreate(text=text, entity_id=entity_id, complete_till=due_ts))
        await message.answer(_TASK_SUCCESS)
    except Exception as exc:
        logger.exception("Failed to create task for entity #%d", entity_id)
        _update_current_span(lf, level="ERROR", status_message=str(exc)[:200])
        await message.answer("⚠️ Ошибка при создании задачи.")
    finally:
        await manager.done()


# ---------------------------------------------------------------------------
# Edit-field Select getter + on_click handler
# ---------------------------------------------------------------------------


async def get_edit_field_options(_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    return {
        "title": _EDIT_FIELD_PROMPT,
        "items": _EDIT_FIELD_ITEMS,
    }


@observe(name="crm-task-edit-field", capture_input=False, capture_output=False)
async def on_edit_field_select(
    _callback: CallbackQuery,
    _widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    lf = get_client()
    if item_id == "text":
        _update_current_span(lf, input={"field": "text", "action": "edit-field-choice"})
        await manager.switch_to(CrmQuickActionSG.edit_task_text)
    elif item_id == "date":
        _update_current_span(lf, input={"field": "date", "action": "edit-field-choice"})
        await manager.switch_to(CrmQuickActionSG.edit_task_date)
    else:
        # Defensive: Select uses fixed item_id_getter, so this branch is
        # logically unreachable, but we keep it observable.
        _update_current_span(lf, output={"action": "cancelled"})


# ---------------------------------------------------------------------------
# Edit task text handler
# ---------------------------------------------------------------------------


@observe(name="crm-task-edit-text", capture_input=False, capture_output=False)
async def on_edit_task_text_input(
    message: Message,
    _widget: MessageInput,
    manager: DialogManager,
) -> None:
    lf = get_client()
    data = manager.dialog_data
    task_id = int(data.get("edit_task_id", 0) or 0)
    text = (message.text or "").strip()

    _update_current_span(lf, input={"task_id": task_id, "field": "text", "action": "edit"})

    if not text:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_EMPTY_TEXT_WARN)
        return

    kommo = _kommo_from_manager(manager)
    if kommo is None:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_NO_CRM)
        await manager.done()
        return

    try:
        await kommo.update_task(task_id, TaskUpdate(text=text))
        await message.answer(_EDIT_SUCCESS)
    except Exception as exc:
        logger.exception("Failed to update task %d text", task_id)
        _update_current_span(lf, level="ERROR", status_message=str(exc)[:200])
        await message.answer("⚠️ Ошибка при обновлении задачи.")
    finally:
        await manager.done()


# ---------------------------------------------------------------------------
# Edit task date handler
# ---------------------------------------------------------------------------


@observe(name="crm-task-edit-date", capture_input=False, capture_output=False)
async def on_edit_task_date_input(
    message: Message,
    _widget: MessageInput,
    manager: DialogManager,
) -> None:
    lf = get_client()
    data = manager.dialog_data
    task_id = int(data.get("edit_task_id", 0) or 0)
    raw = (message.text or "").strip()

    _update_current_span(lf, input={"task_id": task_id, "field": "date", "action": "edit"})

    try:
        dt = datetime.datetime.strptime(raw, "%d.%m.%Y %H:%M")
        dt = dt.replace(tzinfo=datetime.UTC)
        due_ts = int(dt.timestamp())
    except ValueError:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_BAD_DATE_WARN)
        return

    kommo = _kommo_from_manager(manager)
    if kommo is None:
        _update_current_span(lf, output={"action": "cancelled"})
        await message.answer(_NO_CRM)
        await manager.done()
        return

    try:
        await kommo.update_task(task_id, TaskUpdate(complete_till=due_ts))
        await message.answer(_EDIT_SUCCESS)
    except Exception as exc:
        logger.exception("Failed to update task %d due date", task_id)
        _update_current_span(lf, level="ERROR", status_message=str(exc)[:200])
        await message.answer("⚠️ Ошибка при обновлении задачи.")
    finally:
        await manager.done()


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


crm_quick_actions_dialog = Dialog(
    Window(
        Const(_NOTE_PROMPT),
        MessageInput(on_note_text_input, content_types=[ContentType.TEXT]),
        Cancel(Const("✖ Отмена")),
        state=CrmQuickActionSG.waiting_note,
    ),
    Window(
        Const(_TASK_PROMPT),
        MessageInput(on_task_text_input, content_types=[ContentType.TEXT]),
        Cancel(Const("✖ Отмена")),
        state=CrmQuickActionSG.waiting_task,
    ),
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="crm_edit_field",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_edit_field_select,
            ),
        ),
        Cancel(Const("✖ Отмена")),
        getter=get_edit_field_options,
        state=CrmQuickActionSG.edit_task_choose_field,
    ),
    Window(
        Const(_EDIT_TEXT_PROMPT),
        MessageInput(on_edit_task_text_input, content_types=[ContentType.TEXT]),
        Cancel(Const("✖ Отмена")),
        state=CrmQuickActionSG.edit_task_text,
    ),
    Window(
        Const(_EDIT_DATE_PROMPT),
        MessageInput(on_edit_task_date_input, content_types=[ContentType.TEXT]),
        Cancel(Const("✖ Отмена")),
        state=CrmQuickActionSG.edit_task_date,
    ),
    on_start=on_dialog_start,
)
