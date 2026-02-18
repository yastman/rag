"""Tests for client menu dialog."""

from telegram_bot.dialogs.client_menu import client_menu_dialog
from telegram_bot.dialogs.states import ClientMenuSG


def test_client_menu_dialog_exists():
    """Client menu dialog is a valid Dialog."""
    from aiogram_dialog import Dialog

    assert isinstance(client_menu_dialog, Dialog)


def test_client_menu_has_main_window():
    """Client menu has window for ClientMenuSG.main state."""
    windows = client_menu_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ClientMenuSG.main in states
