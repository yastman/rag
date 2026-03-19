"""FAQ dialog — static info pages (aiogram-dialog)."""

from __future__ import annotations

from typing import Any

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Format

from .root_nav import get_main_menu_label, root_menu_button
from .states import FaqSG


async def get_faq_data(i18n: Any = None, **kwargs: Any) -> dict[str, str]:
    """Getter for FAQ content."""
    if i18n is None:
        return {
            "title": "FAQ",
            "btn_back": "Назад",
            "btn_main_menu": get_main_menu_label(),
        }
    return {
        "title": i18n.get("menu-faq"),
        "btn_back": i18n.get("back"),
        "btn_main_menu": get_main_menu_label(i18n),
    }


faq_dialog = Dialog(
    Window(
        Format("{title}"),
        root_menu_button(),
        Cancel(Format("{btn_back}")),
        getter=get_faq_data,
        state=FaqSG.main,
    ),
)
