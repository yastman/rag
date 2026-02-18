"""Client main menu dialog (aiogram-dialog)."""

from __future__ import annotations

from typing import Any

from aiogram_dialog import Dialog, LaunchMode, Window
from aiogram_dialog.widgets.kbd import Column, Start
from aiogram_dialog.widgets.text import Format

from .states import ClientMenuSG, FaqSG, FunnelSG, SettingsSG


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
            "btn_faq": "Полезная информация",
            "btn_settings": "Настройки",
            "btn_manager": "Связаться с менеджером",
        }

    return {
        "greeting": i18n.get("hello", name=name),
        "btn_search": i18n.get("menu-search"),
        "btn_faq": i18n.get("menu-faq"),
        "btn_settings": i18n.get("menu-settings"),
        "btn_manager": i18n.get("menu-manager"),
    }


client_menu_dialog = Dialog(
    Window(
        Format("{greeting}"),
        Column(
            Start(
                Format("{btn_search}"),
                id="funnel",
                state=FunnelSG.property_type,
            ),
            Start(
                Format("{btn_faq}"),
                id="faq",
                state=FaqSG.main,
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
