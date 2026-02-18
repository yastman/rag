"""Settings dialog: language switch, notifications (aiogram-dialog)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column, SwitchTo
from aiogram_dialog.widgets.text import Const, Format

from .states import SettingsSG


logger = logging.getLogger(__name__)

_SUPPORTED_LOCALES = [
    ("ru", "lang-ru"),
    ("en", "lang-en"),
    ("uk", "lang-uk"),
]


async def get_settings_data(i18n: Any = None, **kwargs: Any) -> dict[str, str]:
    """Getter for settings main window."""
    if i18n is None:
        return {"title": "Настройки", "btn_language": "Язык", "btn_back": "Назад"}
    return {
        "title": i18n.get("settings-title"),
        "btn_language": i18n.get("settings-language"),
        "btn_back": i18n.get("back"),
    }


async def get_language_data(i18n: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Getter for language selection window."""
    if i18n is None:
        return {"title": "Язык", "btn_back": "Назад", "languages": _SUPPORTED_LOCALES}

    languages = [(code, i18n.get(label_key)) for code, label_key in _SUPPORTED_LOCALES]
    return {
        "title": i18n.get("settings-language"),
        "btn_back": i18n.get("back"),
        "languages": languages,
    }


async def on_language_selected(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Handle language selection button click."""
    locale = button.widget_id  # widget_id = locale code (ru, en, uk)
    user_service = manager.middleware_data.get("user_service")
    if user_service is not None and callback.from_user:
        try:
            await user_service.set_locale(
                telegram_id=callback.from_user.id,
                locale=locale,
            )
        except Exception:
            logger.warning(
                "Failed to save locale for user %s", callback.from_user.id, exc_info=True
            )
    # Restart dialog to apply new locale
    await manager.done()


settings_dialog = Dialog(
    # Main settings window
    Window(
        Format("{title}"),
        Column(
            SwitchTo(
                Format("{btn_language}"),
                id="lang",
                state=SettingsSG.language,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_settings_data,
        state=SettingsSG.main,
    ),
    # Language selection window
    Window(
        Format("{title}"),
        Column(
            Button(Const("Русский"), id="ru", on_click=on_language_selected),
            Button(Const("English"), id="en", on_click=on_language_selected),
            Button(Const("Українська"), id="uk", on_click=on_language_selected),
        ),
        SwitchTo(Format("{btn_back}"), id="back_to_settings", state=SettingsSG.main),
        getter=get_language_data,
        state=SettingsSG.language,
    ),
)
