"""Tests for settings dialog."""

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
