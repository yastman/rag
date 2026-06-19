"""Tests for settings dialog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.settings import settings_dialog
from telegram_bot.dialogs.states import SettingsSG


def test_settings_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(settings_dialog, Dialog)


def test_settings_has_main_and_language():
    windows = settings_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert SettingsSG.main in states
    assert SettingsSG.language in states


async def test_language_selected_restarts_settings_root():
    """Changing language should restart settings instead of closing the stack."""
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.settings import on_language_selected

    callback = MagicMock()
    callback.from_user.id = 42
    button = MagicMock(widget_id="en")
    manager = AsyncMock()
    manager.middleware_data = {"user_service": AsyncMock()}

    await on_language_selected(callback, button, manager)

    manager.middleware_data["user_service"].set_locale.assert_awaited_once_with(
        telegram_id=42,
        locale="en",
    )
    manager.start.assert_awaited_once_with(SettingsSG.main, mode=StartMode.RESET_STACK)
    manager.done.assert_not_called()


# --- get_settings_data ---


async def test_get_settings_data_with_fake_i18n():
    """get_settings_data uses i18n when provided."""
    from telegram_bot.dialogs.settings import get_settings_data

    i18n = MagicMock()
    i18n.get = MagicMock(
        side_effect=lambda key: {
            "settings-title": "Settings",
            "settings-language": "Language",
            "back": "Back",
        }.get(key, key)
    )

    result = await get_settings_data(i18n=i18n)

    assert result["title"] == "Settings"
    assert result["btn_language"] == "Language"
    assert result["btn_back"] == "Back"
