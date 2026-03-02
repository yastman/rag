"""CRM Task wizard and My Tasks view dialogs (aiogram-dialog) — #697.

Task 6:
- CreateTaskWizard: text → task_type → lead_id → due_date → summary → confirm
- MyTasksView: filter → list with complete/reopen actions
"""

from __future__ import annotations

import datetime
import logging
import operator
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import ManagedTextInput, TextInput
from aiogram_dialog.widgets.kbd import Back, Button, Cancel, Column, Select, Start
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.services.kommo_models import Task

from .states import CreateTaskSG, MyTasksSG, TasksMenuSG


logger = logging.getLogger(__name__)

# --- Constants ---

# Task type options: (label, key)
TASK_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("📞 Звонок", "call"),
    ("🤝 Встреча", "meeting"),
    ("📋 Другое", "other"),
]

# Kommo task_type_id mapping
_TASK_TYPE_ID_MAP: dict[str, int] = {
    "call": 1,
    "meeting": 2,
    "other": 3,
}

# Filter options for My Tasks
FILTER_OPTIONS: list[tuple[str, str]] = [
    ("📋 Все задачи", "all"),
    ("📅 Сегодня", "today"),
    ("⚠️ Просроченные", "overdue"),
]

# Pagination: tasks per page
_PAGE_SIZE = 5


# --- Helpers ---


def task_type_id_from_key(key: str) -> int:
    """Convert task type key to Kommo task_type_id.

    Args:
        key: One of 'call', 'meeting', 'other'.

    Returns:
        Kommo API task_type_id integer.

    Raises:
        KeyError: If key is not recognized.
    """
    return _TASK_TYPE_ID_MAP[key]


def parse_due_date(date_str: str) -> int:
    """Parse DD.MM.YYYY string to Unix timestamp.

    Args:
        date_str: Date string in DD.MM.YYYY format.

    Returns:
        Unix timestamp (int) at end of the given day (23:59:59 UTC).

    Raises:
        ValueError: If format is invalid or date is in the past.
    """
    try:
        dt = datetime.datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except ValueError:
        raise ValueError(f"Неверный формат даты: '{date_str}'. Используйте DD.MM.YYYY")

    # Set to end of day in UTC
    dt_utc = dt.replace(hour=23, minute=59, second=59, tzinfo=datetime.UTC)
    now_utc = datetime.datetime.now(tz=datetime.UTC)

    if dt_utc < now_utc:
        raise ValueError("Срок выполнения не может быть в прошлом")

    return int(dt_utc.timestamp())


def filter_tasks_today(tasks: list[Task]) -> list[Task]:
    """Return tasks due today that are not completed.

    Args:
        tasks: List of Task objects.

    Returns:
        Tasks with complete_till falling on today's date (UTC).
    """
    now = datetime.datetime.now(tz=datetime.UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    result = []
    for task in tasks:
        if task.is_completed:
            continue
        if task.complete_till is None:
            continue
        dt = datetime.datetime.fromtimestamp(task.complete_till, tz=datetime.UTC)
        if today_start <= dt <= today_end:
            result.append(task)
    return result


def filter_tasks_overdue(tasks: list[Task]) -> list[Task]:
    """Return tasks past due that are not completed.

    Args:
        tasks: List of Task objects.

    Returns:
        Active tasks with complete_till in the past.
    """
    now = datetime.datetime.now(tz=datetime.UTC)
    now_ts = int(now.timestamp())

    return [
        task
        for task in tasks
        if not task.is_completed and task.complete_till is not None and task.complete_till < now_ts
    ]


def render_tasks_text(tasks: list[Task]) -> str:
    """Render task list as formatted text for Telegram message.

    Args:
        tasks: List of Task objects to render.

    Returns:
        Formatted string with task cards separated by dividers.
    """
    if not tasks:
        return "Задач нет."

    parts = []
    for task in tasks:
        status_icon = "✅" if task.is_completed else "🔲"
        due_str = "—"
        if task.complete_till:
            dt = datetime.datetime.fromtimestamp(task.complete_till, tz=datetime.UTC)
            due_str = dt.strftime("%d.%m.%Y %H:%M")

        lines = [
            f"{status_icon} *Задача #{task.id}*",
            f"Текст: {task.text or '—'}",
            f"Срок: {due_str}",
        ]
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


# --- Getters ---


async def get_create_task_text_data(**kwargs: Any) -> dict[str, str]:
    """Getter for create-task text input window."""
    return {"title": "✅ Создание задачи\n\nШаг 1/5: Введите описание задачи:"}


async def get_task_type_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for task type selection window."""
    return {
        "title": "✅ Создание задачи\n\nШаг 2/5: Выберите тип задачи:",
        "items": TASK_TYPE_OPTIONS,
    }


async def get_lead_options(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter for lead selection — fetches recent leads from Kommo."""
    kommo = dialog_manager.middleware_data.get("kommo_client")

    lead_items: list[tuple[str, str]] = []

    if kommo is not None:
        try:
            leads = await kommo.search_leads(query="", limit=10)
            for lead in leads[:10]:
                label = f"#{lead.id} {lead.name or '—'}"
                lead_items.append((label, str(lead.id)))
        except Exception:
            logger.exception("Failed to fetch leads for task wizard")

    if not lead_items:
        lead_items = [("— нет доступных сделок —", "0")]

    return {
        "title": "✅ Создание задачи\n\nШаг 3/5: Выберите сделку для привязки:",
        "items": lead_items,
    }


async def get_create_task_due_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, str]:
    """Getter for due date input window."""
    data = dialog_manager.dialog_data
    task_text = data.get("task_text", "—")
    task_type = data.get("task_type_label", "—")
    lead_label = data.get("lead_label", "—")

    return {
        "title": (
            f"✅ Создание задачи\n\n"
            f"Шаг 4/5: Введите срок выполнения (формат DD.MM.YYYY):\n\n"
            f"📝 Задача: {task_text}\n"
            f"📌 Тип: {task_type}\n"
            f"🔗 Сделка: {lead_label}"
        )
    }


async def get_create_task_summary(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, str]:
    """Getter for summary/confirmation window."""
    data = dialog_manager.dialog_data
    task_text = data.get("task_text", "—")
    task_type = data.get("task_type_label", "—")
    lead_label = data.get("lead_label", "—")
    due_date = data.get("due_date_display", "—")

    summary = (
        f"✅ *Подтверждение задачи*\n\n"
        f"📝 Задача: {task_text}\n"
        f"📌 Тип: {task_type}\n"
        f"🔗 Сделка: {lead_label}\n"
        f"📅 Срок: {due_date}\n\n"
        f"Создать задачу?"
    )
    return {"summary": summary}


async def get_filter_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for My Tasks filter selection."""
    return {
        "title": "📋 Мои задачи\n\nВыберите фильтр:",
        "items": FILTER_OPTIONS,
    }


async def get_task_list(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter for task list window — fetches and filters tasks from Kommo."""
    kommo = dialog_manager.middleware_data.get("kommo_client")
    data = dialog_manager.dialog_data
    task_filter = data.get("task_filter", "all")
    page = data.get("page", 0)

    tasks: list[Task] = []
    user_id: int | None = None

    # Get current user ID from middleware
    event_from_user = kwargs.get("event_from_user")
    if event_from_user is not None:
        user_id = event_from_user.id

    if kommo is not None:
        try:
            raw_tasks = await kommo.get_tasks(responsible_user_id=user_id, limit=50)

            if task_filter == "today":
                tasks = filter_tasks_today(raw_tasks)
            elif task_filter == "overdue":
                tasks = filter_tasks_overdue(raw_tasks)
            else:
                tasks = raw_tasks
        except Exception:
            logger.exception("Failed to fetch tasks for My Tasks view")

    # Pagination
    total = len(tasks)
    start = page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    page_tasks = tasks[start:end]

    tasks_text = render_tasks_text(page_tasks)

    # Filter label for header
    filter_labels = {"all": "Все", "today": "Сегодня", "overdue": "Просроченные"}
    filter_label = filter_labels.get(task_filter, "Все")

    # Active tasks for complete select widget
    active_tasks = [
        (f"#{t.id}: {(t.text or '')[:30]}", str(t.id)) for t in page_tasks if not t.is_completed
    ]

    return {
        "title": f"📋 Мои задачи — {filter_label} ({total})",
        "tasks_text": tasks_text,
        "has_prev": page > 0,
        "has_next": end < total,
        "page": page,
        "total": total,
        "active_tasks": active_tasks,
        "has_active": len(active_tasks) > 0,
    }


# --- Handlers ---


async def on_task_text_entered(
    message: Message,
    widget: ManagedTextInput,
    manager: DialogManager,
    value: str,
) -> None:
    """Save task description and advance to task type selection."""
    manager.dialog_data["task_text"] = value.strip()
    await manager.switch_to(CreateTaskSG.task_type)


async def on_task_type_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save task type and advance to lead selection."""
    label_map = {key: label for label, key in TASK_TYPE_OPTIONS}
    manager.dialog_data["task_type_key"] = item_id
    manager.dialog_data["task_type_label"] = label_map.get(item_id, item_id)
    manager.dialog_data["task_type_id"] = task_type_id_from_key(item_id)
    await manager.switch_to(CreateTaskSG.lead_id)


async def on_lead_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save lead selection and advance to due date input."""
    manager.dialog_data["lead_id"] = int(item_id) if item_id != "0" else None
    # Find label from items — store it for summary display
    manager.dialog_data["lead_label"] = f"Сделка #{item_id}" if item_id != "0" else "—"
    await manager.switch_to(CreateTaskSG.due_date)


async def on_due_date_entered(
    message: Message,
    widget: ManagedTextInput,
    manager: DialogManager,
    value: str,
) -> None:
    """Parse due date and advance to summary."""
    try:
        ts = parse_due_date(value.strip())
    except ValueError as exc:
        await message.answer(str(exc))
        return

    manager.dialog_data["due_date_ts"] = ts
    # Store display string
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
    manager.dialog_data["due_date_display"] = dt.strftime("%d.%m.%Y")
    await manager.switch_to(CreateTaskSG.summary)


async def on_due_date_error(
    message: Message,
    widget: ManagedTextInput,
    manager: DialogManager,
    error: ValueError,
) -> None:
    """Handle invalid due date input."""
    await message.answer(f"❌ {error}\n\nВведите дату в формате DD.MM.YYYY:")


async def on_task_confirm(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Create task via Kommo API and close dialog."""
    from telegram_bot.services.kommo_models import TaskCreate

    kommo = manager.middleware_data.get("kommo_client")
    data = manager.dialog_data

    task_text = data.get("task_text", "")
    entity_id = data.get("lead_id")
    due_date_ts = data.get("due_date_ts")
    task_type_id = data.get("task_type_id", 3)

    if kommo is None:
        await callback.answer("CRM недоступен", show_alert=True)
        await manager.done()
        return

    if not task_text or not entity_id or not due_date_ts:
        await callback.answer("Ошибка: не все поля заполнены", show_alert=True)
        return

    try:
        task = await kommo.create_task(
            TaskCreate(
                text=task_text,
                entity_id=entity_id,
                entity_type="leads",
                complete_till=due_date_ts,
                task_type_id=task_type_id,
            )
        )
        await callback.answer(f"✅ Задача #{task.id} создана!", show_alert=True)
    except Exception:
        logger.exception("Failed to create task via Kommo")
        await callback.answer("❌ Ошибка при создании задачи", show_alert=True)

    await manager.done()


async def on_filter_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save filter and switch to task list."""
    manager.dialog_data["task_filter"] = item_id
    manager.dialog_data["page"] = 0
    await manager.switch_to(MyTasksSG.list)


async def on_prev_page(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Go to previous page."""
    page = manager.dialog_data.get("page", 0)
    manager.dialog_data["page"] = max(0, page - 1)


async def on_next_page(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Go to next page."""
    page = manager.dialog_data.get("page", 0)
    manager.dialog_data["page"] = page + 1


async def on_task_complete(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Mark selected task as completed via Kommo API."""
    kommo = manager.middleware_data.get("kommo_client")
    if kommo is None:
        await callback.answer("CRM недоступен", show_alert=True)
        return

    try:
        task_id = int(item_id)
        await kommo.complete_task(task_id)
        await callback.answer(f"✅ Задача #{task_id} выполнена!")
    except Exception:
        logger.exception("Failed to complete task %s", item_id)
        await callback.answer("❌ Не удалось завершить задачу", show_alert=True)


# --- Dialogs ---


create_task_dialog = Dialog(
    # Step 1: Task text input
    Window(
        Format("{title}"),
        TextInput(
            id="task_text_input",
            on_success=on_task_text_entered,
        ),
        Cancel(Const("← Отмена")),
        getter=get_create_task_text_data,
        state=CreateTaskSG.text,
    ),
    # Step 2: Task type selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="task_type_select",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_task_type_selected,
            ),
        ),
        Back(Const("← Назад")),
        getter=get_task_type_options,
        state=CreateTaskSG.task_type,
    ),
    # Step 3: Lead selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="lead_select",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_lead_selected,
            ),
        ),
        Back(Const("← Назад")),
        getter=get_lead_options,
        state=CreateTaskSG.lead_id,
    ),
    # Step 4: Due date input
    Window(
        Format("{title}"),
        TextInput(
            id="due_date_input",
            on_success=on_due_date_entered,
            on_error=on_due_date_error,
        ),
        Back(Const("← Назад")),
        getter=get_create_task_due_data,
        state=CreateTaskSG.due_date,
    ),
    # Step 5: Summary / confirmation
    Window(
        Format("{summary}"),
        Button(Const("✅ Создать"), id="confirm_task", on_click=on_task_confirm),
        Back(Const("← Изменить")),
        Cancel(Const("✖ Отмена")),
        getter=get_create_task_summary,
        state=CreateTaskSG.summary,
    ),
)


my_tasks_dialog = Dialog(
    # Step 1: Filter selection
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="filter_select",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_filter_selected,
            ),
        ),
        Cancel(Const("← Назад")),
        getter=get_filter_options,
        state=MyTasksSG.filter,
    ),
    # Step 2: Task list with pagination and complete action
    Window(
        Format("{title}\n\n{tasks_text}"),
        # Complete task select (shown only when there are active tasks)
        Column(
            Select(
                Format("✅ Выполнить: {item[0]}"),
                id="complete_task_select",
                item_id_getter=operator.itemgetter(1),
                items="active_tasks",
                on_click=on_task_complete,
                when="has_active",
            ),
        ),
        Button(Const("◀ Пред. стр."), id="prev_page", on_click=on_prev_page, when="has_prev"),
        Button(Const("След. стр. ▶"), id="next_page", on_click=on_next_page, when="has_next"),
        Back(Const("← Фильтр")),
        Cancel(Const("✖ Закрыть")),
        getter=get_task_list,
        state=MyTasksSG.list,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Tasks Menu — navigation hub (create + my tasks)
# ─────────────────────────────────────────────────────────────────────────────


async def get_tasks_menu_data(**kwargs: Any) -> dict[str, str]:
    """Getter: tasks navigation hub labels."""
    return {
        "title": "✅ Задачи",
        "btn_create": "➕ Создать задачу",
        "btn_my_tasks": "📋 Мои задачи",
        "btn_back": "← Назад",
    }


tasks_menu_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Start(
                Format("{btn_create}"),
                id="tasks_nav_create",
                state=CreateTaskSG.text,
            ),
            Start(
                Format("{btn_my_tasks}"),
                id="tasks_nav_my",
                state=MyTasksSG.filter,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_tasks_menu_data,
        state=TasksMenuSG.main,
    ),
)
