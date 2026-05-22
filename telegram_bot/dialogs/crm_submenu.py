"""CRM navigation hub dialog for managers (aiogram-dialog) — #697.

Refactored from action-dispatching menu to a navigation hub that routes
to dedicated wizard dialogs for each CRM operation.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Cancel, Column, Start
from aiogram_dialog.widgets.text import Format

from .states import (
    AIAdvisorSG,
    ContactsMenuSG,
    CreateNoteSG,
    CreateTaskSG,
    CRMMenuSG,
    LeadsMenuSG,
    MyTasksSG,
    SettingsSG,
)


logger = logging.getLogger(__name__)


async def get_crm_menu_data(
    i18n: Any = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Getter: provide CRM navigation hub text (fallback without i18n)."""
    return {
        "title": "CRM — Панель менеджера",
        "btn_leads": "📋 Сделки",
        "btn_contacts": "👤 Контакты",
        "btn_tasks": "✅ Создать задачу",
        "btn_my_tasks": "📋 Мои задачи",
        "btn_note": "📝 Заметка",
        "btn_ai_advisor": "🤖 AI-Советник",
        "btn_settings": "⚙️ Настройки",
        "btn_back": "← Назад",
    }


crm_submenu_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Start(
                Format("{btn_leads}"),
                id="crm_nav_leads",
                state=LeadsMenuSG.main,
            ),
            Start(
                Format("{btn_contacts}"),
                id="crm_nav_contacts",
                state=ContactsMenuSG.main,
            ),
            Start(
                Format("{btn_tasks}"),
                id="crm_nav_tasks",
                state=CreateTaskSG.text,
            ),
            Start(
                Format("{btn_my_tasks}"),
                id="crm_nav_my_tasks",
                state=MyTasksSG.filter,
            ),
            Start(
                Format("{btn_note}"),
                id="crm_nav_note",
                state=CreateNoteSG.text,
            ),
            Start(
                Format("{btn_ai_advisor}"),
                id="crm_nav_ai",
                state=AIAdvisorSG.main,
            ),
            Start(
                Format("{btn_settings}"),
                id="crm_nav_settings",
                state=SettingsSG.main,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_crm_menu_data,
        state=CRMMenuSG.main,
    ),
)
