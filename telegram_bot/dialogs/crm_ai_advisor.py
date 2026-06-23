"""AI Advisor dialog — LLM-powered manager insights (#731).

Two actions:
- План на день (daily_plan): Combined briefing with action plan
- Советы по сделкам (deal_tips): Analysis of stale deals + task tips

Loading state pattern:
  on_advisor_action → switch_to(loading) + asyncio.create_task(_fetch_result)
  _fetch_result → bg.update(result_text) + bg.switch_to(result)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column, Select
from aiogram_dialog.widgets.text import Const, Format

from .states import AIAdvisorSG


logger = logging.getLogger(__name__)

_ADVISOR_ACTIONS: list[tuple[str, str]] = [
    ("📋 План на день", "daily_plan"),
    ("💡 Советы по сделкам", "deal_tips"),
]


async def get_advisor_menu(**kwargs: Any) -> dict[str, Any]:
    """Getter for the AI advisor main window."""
    return {
        "title": "🤖 AI-Советник\n\nВыберите действие:",
        "items": _ADVISOR_ACTIONS,
    }


async def _fetch_advisor_result(
    bg: Any,
    action: str,
    advisor: Any | None,
    manager_id: int | None,
) -> None:
    """Background task: call advisor service and transition to result state."""
    if not advisor:
        result = "AI-Советник недоступен. Проверьте настройки CRM."
    else:
        try:
            if action == "daily_plan":
                result = await advisor.get_daily_plan(manager_id)
            elif action == "deal_tips":
                result = await advisor.get_deal_and_task_tips(manager_id)
            else:
                result = "Неизвестное действие."
        except Exception:
            logger.exception("AI Advisor failed for action=%s", action)
            result = "❌ Ошибка при генерации ответа. Попробуйте позже."

    try:
        await bg.update({"result_text": result})
        await bg.switch_to(AIAdvisorSG.result)
    except Exception:
        logger.exception("Failed to update advisor result via bg manager")


async def on_advisor_action(
    callback: CallbackQuery,
    _widget: Any,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Handle advisor action selection — switch to loading, fetch result in background."""
    manager.dialog_data["advisor_action"] = item_id
    await manager.switch_to(AIAdvisorSG.loading)

    advisor = manager.middleware_data.get("ai_advisor_service")
    config = manager.middleware_data.get("bot_config")
    manager_id: int | None = getattr(config, "kommo_responsible_user_id", None) if config else None

    bg = manager.bg()
    task = asyncio.create_task(_fetch_advisor_result(bg, item_id, advisor, manager_id))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


async def get_loading_data(**kwargs: Any) -> dict[str, Any]:
    """Getter for loading window — shows progress message."""
    return {"loading_text": "⏳ Анализирую ваши данные...\nЭто может занять несколько секунд."}


async def get_advisor_result(
    dialog_manager: DialogManager | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for result window — reads pre-fetched result from dialog_data."""
    if dialog_manager is None:
        return {"result_text": "—"}
    return {"result_text": dialog_manager.dialog_data.get("result_text", "—")}


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
        Format("{loading_text}"),
        getter=get_loading_data,
        state=AIAdvisorSG.loading,
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
