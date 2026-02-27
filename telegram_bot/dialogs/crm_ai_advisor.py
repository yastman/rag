"""AI Advisor dialog — LLM-powered manager insights (#697).

Four actions available:
- Новые лиды (leads): LLM prioritization of recent leads
- Мои задачи (tasks): LLM prioritization of open tasks
- Сделки в работе (stale): Analysis of deals with no activity 5+ days
- Полный брифинг (briefing): Combined morning digest (cached 10 min)
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column, Select
from aiogram_dialog.widgets.text import Const, Format

from .states import AIAdvisorSG


logger = logging.getLogger(__name__)

_ADVISOR_ACTIONS: list[tuple[str, str]] = [
    ("🔥 Новые лиды", "leads"),
    ("✅ Мои задачи", "tasks"),
    ("📊 Сделки в работе", "stale"),
    ("📋 Полный брифинг", "briefing"),
]


async def get_advisor_menu(**kwargs: Any) -> dict[str, Any]:
    """Getter for the AI advisor main window."""
    return {
        "title": "🤖 AI-Советник",
        "items": _ADVISOR_ACTIONS,
    }


async def on_advisor_action(
    callback: CallbackQuery,
    widget: Any,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Handle advisor action selection — store action and switch to result."""
    manager.dialog_data["advisor_action"] = item_id
    await manager.switch_to(AIAdvisorSG.result)


async def get_advisor_result(
    dialog_manager: DialogManager | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for result window — invokes the appropriate advisor method."""
    if dialog_manager is None:
        return {"result_text": "—"}

    action = dialog_manager.dialog_data.get("advisor_action", "")
    advisor = dialog_manager.middleware_data.get("ai_advisor_service")

    if not advisor:
        return {"result_text": ("AI-Советник недоступен. Проверьте настройки CRM.")}

    # Resolve manager_id from middleware config
    config = dialog_manager.middleware_data.get("bot_config")
    manager_id: int | None = getattr(config, "kommo_responsible_user_id", None) if config else None

    action_map = {
        "leads": advisor.get_prioritized_leads,
        "tasks": advisor.get_prioritized_tasks,
        "stale": advisor.get_stale_deals,
        "briefing": advisor.get_full_briefing,
    }
    func = action_map.get(action)

    try:
        if func:
            result = await func(manager_id)
        else:
            result = "Неизвестное действие."
    except Exception:
        logger.exception("AI Advisor failed for action=%s", action)
        result = "❌ Ошибка при генерации ответа."

    return {"result_text": result}


async def on_advisor_back(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Return to advisor main menu."""
    await manager.switch_to(AIAdvisorSG.main)


advisor_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="advisor_action_select",
                item_id_getter=lambda item: item[1],
                items="items",
                on_click=on_advisor_action,
            ),
        ),
        Cancel(Const("← Назад")),
        getter=get_advisor_menu,
        state=AIAdvisorSG.main,
    ),
    Window(
        Format("{result_text}"),
        Button(
            Const("← К меню советника"),
            id="advisor_back",
            on_click=on_advisor_back,
        ),
        Cancel(Const("← CRM")),
        getter=get_advisor_result,
        state=AIAdvisorSG.result,
    ),
)
