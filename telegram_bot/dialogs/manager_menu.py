"""Manager main menu dialog (aiogram-dialog).

Promotes CRM navigation hub (#697) to the root manager menu.
All wizard Start buttons are directly accessible from /start.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, LaunchMode, Window
from aiogram_dialog.widgets.kbd import Button, Column, Start
from aiogram_dialog.widgets.text import Format

from .states import (
    AIAdvisorSG,
    ContactsMenuSG,
    CreateNoteSG,
    CreateTaskSG,
    LeadsMenuSG,
    ManagerMenuSG,
    MyTasksSG,
    SettingsSG,
)


logger = logging.getLogger(__name__)

# Maps button widget_id -> query text sent to agent
_BUTTON_QUERIES: dict[str, str] = {
    "mgr_search": "Поиск по базе знаний",
}


async def get_manager_menu_data(
    event_from_user: Any = None,
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Getter: provide localized manager menu text."""
    name = ""
    if event_from_user is not None:
        name = getattr(event_from_user, "first_name", "") or ""

    if i18n is None:
        return {
            "greeting": f"📊 CRM — Привет, {name}!",
            "btn_leads": "📋 Сделки",
            "btn_contacts": "👤 Контакты",
            "btn_tasks": "✅ Создать задачу",
            "btn_my_tasks": "📋 Мои задачи",
            "btn_note": "📝 Заметка",
            "btn_ai_advisor": "🤖 AI-Советник",
            "btn_search": "🔍 Поиск по базе",
            "btn_settings": "⚙️ Настройки",
        }

    return {
        "greeting": i18n.get("mgr-hello", name=name),
        "btn_leads": i18n.get("mgr-leads"),
        "btn_contacts": i18n.get("mgr-contacts"),
        "btn_tasks": i18n.get("mgr-tasks-create"),
        "btn_my_tasks": i18n.get("mgr-my-tasks"),
        "btn_note": i18n.get("mgr-note"),
        "btn_ai_advisor": i18n.get("mgr-ai-advisor"),
        "btn_search": i18n.get("mgr-search"),
        "btn_settings": i18n.get("mgr-settings"),
    }


async def on_manager_action(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle manager menu action button click: close dialog, dispatch query to agent."""
    query_text = _BUTTON_QUERIES.get(button.widget_id, "")
    bot_instance = manager.middleware_data.get("property_bot")
    locale = manager.middleware_data.get("locale", "ru")
    await manager.done()
    if bot_instance is not None and query_text:
        try:
            await bot_instance.handle_menu_action(callback, query_text, locale=locale)
        except Exception:
            logger.exception("handle_menu_action failed for widget_id=%s", button.widget_id)


manager_menu_dialog = Dialog(
    Window(
        Format("{greeting}"),
        Column(
            Start(
                Format("{btn_leads}"),
                id="mgr_leads",
                state=LeadsMenuSG.main,
            ),
            Start(
                Format("{btn_contacts}"),
                id="mgr_contacts",
                state=ContactsMenuSG.main,
            ),
            Start(
                Format("{btn_tasks}"),
                id="mgr_tasks",
                state=CreateTaskSG.text,
            ),
            Start(
                Format("{btn_my_tasks}"),
                id="mgr_my_tasks",
                state=MyTasksSG.filter,
            ),
            Start(
                Format("{btn_note}"),
                id="mgr_note",
                state=CreateNoteSG.text,
            ),
            Start(
                Format("{btn_ai_advisor}"),
                id="mgr_ai_advisor",
                state=AIAdvisorSG.main,
            ),
            Button(
                Format("{btn_search}"),
                id="mgr_search",
                on_click=on_manager_action,
            ),
            Start(
                Format("{btn_settings}"),
                id="mgr_settings",
                state=SettingsSG.main,
            ),
        ),
        getter=get_manager_menu_data,
        state=ManagerMenuSG.main,
    ),
    launch_mode=LaunchMode.ROOT,
)
