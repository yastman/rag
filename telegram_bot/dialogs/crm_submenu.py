"""CRM submenu dialog for managers (aiogram-dialog)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column
from aiogram_dialog.widgets.text import Format

from .states import CrmSubmenuSG


logger = logging.getLogger(__name__)

# Maps button widget_id -> query text sent to agent
_BUTTON_QUERIES: dict[str, str] = {
    "crm_create_deal": "Создай сделку",
    "crm_create_contact": "Создай контакт",
    "crm_add_note": "Добавь заметку к сделке",
    "crm_create_task": "Создай задачу",
    "crm_pipelines": "Покажи pipelines",
}


async def get_crm_submenu_data(
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Getter: provide localized CRM submenu text."""
    if i18n is None:
        return {
            "title": "CRM",
            "btn_create_deal": "Создать сделку",
            "btn_create_contact": "Создать контакт",
            "btn_add_note": "Добавить заметку",
            "btn_create_task": "Создать задачу",
            "btn_pipelines": "Pipelines",
            "btn_back": "Назад",
        }

    return {
        "title": i18n.get("crm-title"),
        "btn_create_deal": i18n.get("crm-create-deal"),
        "btn_create_contact": i18n.get("crm-create-contact"),
        "btn_add_note": i18n.get("crm-add-note"),
        "btn_create_task": i18n.get("crm-create-task"),
        "btn_pipelines": i18n.get("crm-pipelines"),
        "btn_back": i18n.get("back"),
    }


async def on_crm_action(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle CRM action button click: close dialog, dispatch query to agent."""
    query_text = _BUTTON_QUERIES.get(button.widget_id, "")
    bot_instance = manager.middleware_data.get("property_bot")
    locale = manager.middleware_data.get("locale", "ru")
    await manager.done()
    if bot_instance is not None and query_text:
        try:
            await bot_instance.handle_menu_action(callback, query_text, locale=locale)
        except Exception:
            logger.exception("handle_menu_action failed for widget_id=%s", button.widget_id)


crm_submenu_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Button(
                Format("{btn_create_deal}"),
                id="crm_create_deal",
                on_click=on_crm_action,
            ),
            Button(
                Format("{btn_create_contact}"),
                id="crm_create_contact",
                on_click=on_crm_action,
            ),
            Button(
                Format("{btn_add_note}"),
                id="crm_add_note",
                on_click=on_crm_action,
            ),
            Button(
                Format("{btn_create_task}"),
                id="crm_create_task",
                on_click=on_crm_action,
            ),
            Button(
                Format("{btn_pipelines}"),
                id="crm_pipelines",
                on_click=on_crm_action,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_crm_submenu_data,
        state=CrmSubmenuSG.main,
    ),
)
