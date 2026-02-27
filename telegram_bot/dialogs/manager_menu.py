"""Manager main menu dialog (aiogram-dialog)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, LaunchMode, Window
from aiogram_dialog.widgets.kbd import Button, Column, Start
from aiogram_dialog.widgets.text import Format

from .states import CRMMenuSG, ManagerMenuSG, SettingsSG


logger = logging.getLogger(__name__)

# Maps button widget_id -> query text sent to agent
_BUTTON_QUERIES: dict[str, str] = {
    "mgr_deals": "Покажи мои сделки",
    "mgr_contacts": "Поиск контактов",
    "mgr_new_deal": "Создай новую сделку",
    "mgr_funnel_stats": "Покажи статистику воронки",
    "mgr_hot_leads": "Покажи горячие лиды",
    "mgr_tasks": "Покажи мои задачи",
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
            "greeting": f"Привет, {name}! Панель менеджера.",
            "btn_deals": "Мои сделки",
            "btn_contacts": "Поиск контактов",
            "btn_new_deal": "Новая сделка",
            "btn_funnel_stats": "Воронка продаж",
            "btn_hot_leads": "Горячие лиды",
            "btn_tasks": "Задачи",
            "btn_crm": "CRM",
            "btn_search": "Поиск по базе",
            "btn_settings": "Настройки",
        }

    return {
        "greeting": i18n.get("mgr-hello", name=name),
        "btn_deals": i18n.get("mgr-deals"),
        "btn_contacts": i18n.get("mgr-contacts"),
        "btn_new_deal": i18n.get("mgr-new-deal"),
        "btn_funnel_stats": i18n.get("mgr-funnel-stats"),
        "btn_hot_leads": i18n.get("mgr-hot-leads"),
        "btn_tasks": i18n.get("mgr-tasks"),
        "btn_crm": i18n.get("mgr-crm-submenu"),
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
            Button(
                Format("{btn_deals}"),
                id="mgr_deals",
                on_click=on_manager_action,
            ),
            Button(
                Format("{btn_contacts}"),
                id="mgr_contacts",
                on_click=on_manager_action,
            ),
            Button(
                Format("{btn_new_deal}"),
                id="mgr_new_deal",
                on_click=on_manager_action,
            ),
            Button(
                Format("{btn_funnel_stats}"),
                id="mgr_funnel_stats",
                on_click=on_manager_action,
            ),
            Button(
                Format("{btn_hot_leads}"),
                id="mgr_hot_leads",
                on_click=on_manager_action,
            ),
            Button(
                Format("{btn_tasks}"),
                id="mgr_tasks",
                on_click=on_manager_action,
            ),
            Start(
                Format("{btn_crm}"),
                id="mgr_crm",
                state=CRMMenuSG.main,
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
