"""Tests for FAQ dialog."""

from telegram_bot.dialogs.faq import faq_dialog
from telegram_bot.dialogs.states import FaqSG


def test_faq_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(faq_dialog, Dialog)


def test_faq_has_main_window():
    windows = faq_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FaqSG.main in states
