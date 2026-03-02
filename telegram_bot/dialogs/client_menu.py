"""Client main menu dialog (aiogram-dialog)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, LaunchMode, Window
from aiogram_dialog.widgets.kbd import Button, Column, Start
from aiogram_dialog.widgets.text import Format

from .states import ClientMenuSG, FaqSG, FunnelSG, SettingsSG


logger = logging.getLogger(__name__)

# Maps button widget_id -> query text sent to agent
_BUTTON_QUERIES: dict[str, str] = {
    "catalog": "Покажи каталог объектов",
    "favorites": "Покажи мои подборки",
    "booking": "Хочу записаться на показ недвижимости",
    "mortgage": "Рассчитай ипотеку",
    "my_leads": "Покажи мои заявки",
    "manager": "Соедини с менеджером",
}


async def get_menu_data(
    callback: Any = None,
    event_from_user: Any = None,
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Getter: provide localized menu text."""
    name = ""
    if event_from_user is not None:
        name = getattr(event_from_user, "first_name", "") or ""

    if i18n is None:
        # Fallback if i18n not injected (e.g., tests)
        return {
            "greeting": f"Привет, {name}!",
            "btn_search": "Подобрать недвижимость",
            "btn_catalog": "Каталог объектов",
            "btn_favorites": "Мои подборки",
            "btn_booking": "Записаться на показ",
            "btn_mortgage": "Рассчитать ипотеку",
            "btn_my_leads": "Мои заявки",
            "btn_faq": "Полезная информация",
            "btn_manager": "Связаться с менеджером",
            "btn_settings": "Настройки",
        }

    return {
        "greeting": i18n.get("hello", name=name),
        "btn_search": i18n.get("menu-search"),
        "btn_catalog": i18n.get("menu-catalog"),
        "btn_favorites": i18n.get("menu-favorites"),
        "btn_booking": i18n.get("menu-booking"),
        "btn_mortgage": i18n.get("menu-mortgage"),
        "btn_my_leads": i18n.get("menu-my-leads"),
        "btn_faq": i18n.get("menu-faq"),
        "btn_manager": i18n.get("menu-manager"),
        "btn_settings": i18n.get("menu-settings"),
    }


async def on_menu_action(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle action button click: close dialog, dispatch query to agent."""
    query_text = _BUTTON_QUERIES.get(button.widget_id, "")
    bot_instance = manager.middleware_data.get("property_bot")
    locale = manager.middleware_data.get("locale", "ru")
    await manager.done()
    if bot_instance is not None and query_text:
        try:
            await bot_instance.handle_menu_action(callback, query_text, locale=locale)
        except Exception:
            logger.exception("handle_menu_action failed for widget_id=%s", button.widget_id)


client_menu_dialog = Dialog(
    Window(
        Format("{greeting}"),
        Column(
            Start(
                Format("{btn_search}"),
                id="funnel",
                state=FunnelSG.city,
            ),
            Button(
                Format("{btn_catalog}"),
                id="catalog",
                on_click=on_menu_action,
            ),
            Button(
                Format("{btn_favorites}"),
                id="favorites",
                on_click=on_menu_action,
            ),
            Button(
                Format("{btn_booking}"),
                id="booking",
                on_click=on_menu_action,
            ),
            Button(
                Format("{btn_mortgage}"),
                id="mortgage",
                on_click=on_menu_action,
            ),
            Button(
                Format("{btn_my_leads}"),
                id="my_leads",
                on_click=on_menu_action,
            ),
            Start(
                Format("{btn_faq}"),
                id="faq",
                state=FaqSG.main,
            ),
            Button(
                Format("{btn_manager}"),
                id="manager",
                on_click=on_menu_action,
            ),
            Start(
                Format("{btn_settings}"),
                id="settings",
                state=SettingsSG.main,
            ),
        ),
        getter=get_menu_data,
        state=ClientMenuSG.main,
    ),
    launch_mode=LaunchMode.ROOT,
)
